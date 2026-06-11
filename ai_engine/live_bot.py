import os
import sys
import time
import logging
import httpx
from datetime import datetime, timezone
from pathlib import Path

# Them thu muc goc vao PYTHONPATH de co the import config
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Import cau hinh
try:
    import MetaTrader5 as mt5
    from backend.config import settings
except ImportError as e:
    print(f"[ERROR] Loi: Thieu thu vien hoac cau hinh. Chi tiet: {str(e)}")
    sys.exit(1)

# Thiet lap Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("live_bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("live_bot")

# Cau hinh API Endpoint va Token
API_URL = "http://127.0.0.1:8000/api/webhook"
SECRET_TOKEN = settings.SECRET_WEBHOOK_TOKEN
SYMBOL = "XAUUSD"
TIMEFRAME_STR = "M1"  # Dat mac dinh M1 de test nhanh tren terminal user
TIMEFRAME = mt5.TIMEFRAME_M5 if TIMEFRAME_STR == "M5" else mt5.TIMEFRAME_M1

class LiveBot:
    def __init__(self):
        self.last_bar_time = 0
        self.is_connected = False

    def connect_mt5(self) -> bool:
        """Ket noi den MT5 Terminal thuc te tren may"""
        if mt5.initialize():
            logger.info("[MT5] Ket noi thanh cong den MT5 Terminal thuc te tren may!")
            if settings.MT5_LOGIN > 0:
                authorized = mt5.login(
                    login=settings.MT5_LOGIN,
                    password=settings.MT5_PASSWORD,
                    server=settings.MT5_SERVER
                )
                if not authorized:
                    logger.error(f"[MT5] [ERROR] Dang nhap tai khoan #{settings.MT5_LOGIN} that bai: {mt5.last_error()}")
                    return False
                logger.info(f"[MT5] [SUCCESS] Dang nhap thanh cong tai khoan MT5 #{settings.MT5_LOGIN}")
            
            self.is_connected = True
            return True
        else:
            logger.error(f"[MT5] [ERROR] Khoi dong MT5 Terminal that bai: {mt5.last_error()}")
            self.is_connected = False
            return False

    def get_indicators(self) -> tuple[float, float, float, float]:
        """Lay 150 nen gan nhat va tinh toan RSI, EMA20, ATR"""
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 150)
        if rates is None or len(rates) < 50:
            logger.warning(f"[MT5] [WARNING] Khong lay duoc du lieu nen cho {SYMBOL}")
            return None

        import pandas as pd
        import numpy as np

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))

        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(14).mean()

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]     # Nen vua dong cua
        prev_prev_row = df.iloc[-3] # Nen truoc do
        
        return (
            float(prev_row["close"]), 
            float(prev_row["rsi"]), 
            float(prev_prev_row["rsi"]),
            float(prev_row["ema20"]), 
            float(prev_row["atr"])
        )

    def send_signal_to_webhook(self, action: str, price: float, sl: float, tp: float):
        """Gui POST Request chua tin hieu giao dich sang FastAPI Webhook"""
        payload = {
            "strategy_name": "RSI_EMA_Cross",
            "symbol": SYMBOL,
            "action": action,
            "price": price,
            "stop_loss": sl,
            "take_profit": tp,
            "token": SECRET_TOKEN
        }
        
        logger.info(f"[API] Dang gui tin hieu {action} len API Gateway Webhook...")
        try:
            with httpx.Client() as client:
                response = client.post(API_URL, json=payload, timeout=10.0)
                if response.status_code == 201:
                    logger.info(f"[API] [SUCCESS] Webhook phan hoi thanh cong: {response.json()}")
                else:
                    logger.error(f"[API] [ERROR] Loi phan hoi Webhook ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"[API] [ERROR] Khong ket noi duoc den Webhook API Gateway: {str(e)}")

    def check_for_signal(self):
        """Kiem tra dieu kien giao dich khi co nen moi vua dong cua"""
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 1)
        if rates is None or len(rates) == 0:
            return

        current_bar_time = int(rates[0][0])
        
        if self.last_bar_time == 0:
            self.last_bar_time = current_bar_time
            logger.info(f"[BOT] Bat dau theo doi nen {TIMEFRAME_STR} cua Vang. Cho nen moi dong cua...")
            return

        if current_bar_time <= self.last_bar_time:
            return

        logger.info(f"[BOT] Phat henen {TIMEFRAME_STR} moi mo cua. Tien hanh quet tin hieu giao dich...")
        self.last_bar_time = current_bar_time

        indicator_data = self.get_indicators()
        if not indicator_data:
            return

        close_price, rsi_val, prev_rsi_val, ema_val, atr_val = indicator_data
        logger.info(f"[BOT] Ket qua nen vua dong: Gia dong={close_price:.2f} | RSI={rsi_val:.2f} (Truoc do={prev_rsi_val:.2f}) | EMA20={ema_val:.2f} | ATR={atr_val:.2f}")

        sl_distance = 2.0 * atr_val
        tp_distance = 3.0 * atr_val

        # BUY: RSI nen truoc do qua ban (< 35) + Gia dong nen vua dong cua vuot EMA20
        if prev_rsi_val < 35 and close_price > ema_val:
            sl = close_price - sl_distance
            tp = close_price + tp_distance
            logger.info(f"[BOT] [SIGNAL] TIN HIEU BUY! Gia dong vuot EMA20 khi RSI truoc do qua ban. SL={sl:.2f}, TP={tp:.2f}")
            self.send_signal_to_webhook("BUY", close_price, sl, tp)

        # SELL: RSI nen truoc do qua mua (> 65) + Gia dong nen vua dong cua cat duoi EMA20
        elif prev_rsi_val > 65 and close_price < ema_val:
            sl = close_price + sl_distance
            tp = close_price - tp_distance
            logger.info(f"[BOT] [SIGNAL] TIN HIEU SELL! Gia dong duoi EMA20 khi RSI truoc do qua mua. SL={sl:.2f}, TP={tp:.2f}")
            self.send_signal_to_webhook("SELL", close_price, sl, tp)
        else:
            logger.info("[BOT] Khong co tin hieu thoa man chien luoc. Cho nen tiep theo...")

    def run(self):
        """Vong lap chinh cua Bot chay lien tuc"""
        if not self.connect_mt5():
            logger.error("[MT5] [ERROR] Khong the ket noi voi MT5. Vui long mo MT5 Terminal tren may!")
            return

        logger.info(f"[BOT] Bot phat tin hieu Live XAU/USD ({TIMEFRAME_STR}) dang hoat dong...")
        logger.info("[BOT] Vui long dam bao Server Backend FastAPI da duoc bat de nhan tin hieu!")

        try:
            while True:
                if not mt5.terminal_info():
                    logger.warning("[MT5] [WARNING] Mat ket noi voi MT5. Dang thu ket noi lai...")
                    self.connect_mt5()
                    time.sleep(5)
                    continue

                self.check_for_signal()
                time.sleep(2)
        except KeyboardInterrupt:
            logger.info("[BOT] Da dung Bot phat tin hieu.")
        finally:
            mt5.shutdown()

if __name__ == "__main__":
    bot = LiveBot()
    bot.run()
