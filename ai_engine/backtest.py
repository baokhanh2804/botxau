import os
import random
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ai_engine.news_fetcher import news_fetcher

logger = logging.getLogger("botxau.backtest")
logging.basicConfig(level=logging.INFO)

DATA_DIR = Path(__file__).resolve().parent / "data"
os.makedirs(DATA_DIR, exist_ok=True)
BACKTEST_CSV = DATA_DIR / "backtest_trades.csv"

class BacktestEngine:
    def __init__(self):
        self.symbol = "XAUUSD"

    def generate_synthetic_data(self, days: int = 180) -> pd.DataFrame:
        """
        Tạo dữ liệu giá Vàng giả lập M5 chất lượng cao phục vụ Backtest.
        Mô phỏng chân thực:
        - Biến động theo phiên (Á, Âu, Mỹ).
        - Tin tức đỏ giật mạnh (News Spikes).
        - Spread giãn nở theo khung giờ và biến động.
        """
        logger.info(f"📈 Đang tạo {days} ngày dữ liệu nến M5 giả lập cho Vàng...")
        
        # Cấu hình chuỗi thời gian
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        time_index = pd.date_range(start=start_time, end=end_time, freq="5min")
        
        # Giá cơ sở của Vàng
        base_price = 2300.0
        prices = []
        
        # Thiết lập biến động theo phiên (Giờ UTC)
        # Á: 00h - 08h (Vol thấp: 0.1)
        # Âu: 08h - 13h (Vol trung bình: 0.3)
        # Mỹ: 13h - 21h (Vol cao: 0.6)
        # Giao phiên: 21h - 24h (Vol rất thấp: 0.05)
        
        for t in time_index:
            # 1. Tính độ biến động theo giờ
            hour = t.hour
            if 0 <= hour < 8:
                volatility = 0.15
            elif 8 <= hour < 13:
                volatility = 0.35
            elif 13 <= hour < 21:
                volatility = 0.75
                # Tăng volatily mạnh nếu trùng giờ ra tin Mỹ lúc 13:30 hoặc 19:00
                if (t.hour == 13 and t.minute == 30) or (t.hour == 19 and t.minute == 0):
                    volatility = 4.5
            else:
                volatility = 0.10

            # 2. Tạo nến OHLC
            # Sinh bước đi ngẫu nhiên (Random walk)
            change = np.random.normal(0, volatility)
            
            # Thêm xung động giật giá nếu trùng lịch tin tức đỏ thực tế
            ts = t.timestamp()
            if news_fetcher.is_major_news_near(ts, threshold_minutes=5):
                # Giật giá mạnh theo một hướng ngẫu nhiên
                change += random.choice([-5.0, -3.5, 3.5, 5.0])
                
            open_p = base_price
            close_p = base_price + change
            high_p = max(open_p, close_p) + abs(np.random.normal(0, volatility * 0.5))
            low_p = min(open_p, close_p) - abs(np.random.normal(0, volatility * 0.5))
            
            # Cập nhật giá cơ sở cho nến sau
            base_price = close_p
            
            # Giả lập Spread (points - 1 point = 0.01$)
            # Spread trung bình phiên Á/Âu: 15-25 points, phiên Mỹ: 12-20 points.
            # Spread giãn lúc giao phiên (21h-22h) hoặc lúc tin ra: lên tới 60-120 points.
            base_spread = 15
            if 21 <= hour <= 22:
                base_spread = random.randint(50, 90)
            elif news_fetcher.is_major_news_near(ts, threshold_minutes=15):
                base_spread = random.randint(40, 110)
            else:
                base_spread = random.randint(12, 22)
                
            prices.append({
                "time": t,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "spread": base_spread
            })
            
        df = pd.DataFrame(prices)
        df.set_index("time", inplace=True)
        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Tính các chỉ báo kỹ thuật cơ bản làm đặc trưng cho AI"""
        # 1. EMA 20 và EMA 200
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
        df["dist_ema200"] = df["close"] - df["ema200"]

        # 2. RSI 14
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))

        # 3. ATR 14 (Average True Range)
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df["atr"] = true_range.rolling(14).mean()
        
        # Điền các giá trị NaN
        df.ffill(inplace=True)
        df.bfill(inplace=True)
        return df

    def run_backtest(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Mô phỏng chiến lược giao dịch gốc (Primary Strategy):
        - BUY: RSI < 30 và giá vượt lên trên EMA20.
        - SELL: RSI > 70 và giá cắt xuống dưới EMA20.
        - Stop Loss = 2 * ATR. Take Profit = 3 * ATR (R:R = 1.5).
        - Trích xuất toàn bộ Features môi trường lúc vào lệnh và gắn nhãn (Label).
        """
        logger.info("🤖 Đang chạy mô phỏng chiến lược giao dịch để thu thập dữ liệu lệnh...")
        
        trades = []
        in_position = False
        pos_type = None # "BUY" hoặc "SELL"
        entry_price = 0.0
        entry_time = None
        sl = 0.0
        tp = 0.0
        
        # Các đặc trưng lưu giữ khi vào lệnh
        trade_features = {}

        # Duyệt qua từng nến
        for i in range(200, len(df)):
            curr_row = df.iloc[i]
            prev_row = df.iloc[i-1]
            curr_time = df.index[i]
            
            # 1. Nếu đang có lệnh mở, kiểm tra xem có chạm SL hoặc TP không
            if in_position:
                # Kiểm tra nến hiện tại có quét qua SL hoặc TP không
                is_closed = False
                pnl_points = 0.0
                
                if pos_type == "BUY":
                    if curr_row["low"] <= sl:
                        is_closed = True
                        close_price = sl
                        pnl_points = sl - entry_price
                        label = 1 # THUA (Chạm SL)
                    elif curr_row["high"] >= tp:
                        is_closed = True
                        close_price = tp
                        pnl_points = tp - entry_price
                        label = 0 # THẮNG (Chạm TP)
                else: # SELL
                    if curr_row["high"] <= sl: # stop loss cho sell là mức giá thấp hơn? Không, SL của Sell là ở trên cao (giá tăng thì lỗ).
                        # Sửa logic SL/TP của Sell:
                        # Với SELL: Giá tăng lên >= sl -> Chạm SL (Thua), Giá giảm xuống <= tp -> Chạm TP (Thắng)
                        pass
                    
                # Thực hiện logic kiểm tra SL/TP chính xác:
                if pos_type == "BUY":
                    if curr_row["low"] <= sl:
                        trades.append({**trade_features, "label": 1, "close_price": sl, "close_time": curr_time, "pnl": -abs(entry_price - sl) * 100})
                        in_position = False
                    elif curr_row["high"] >= tp:
                        trades.append({**trade_features, "label": 0, "close_price": tp, "close_time": curr_time, "pnl": abs(tp - entry_price) * 100})
                        in_position = False
                elif pos_type == "SELL":
                    if curr_row["high"] >= sl:
                        trades.append({**trade_features, "label": 1, "close_price": sl, "close_time": curr_time, "pnl": -abs(sl - entry_price) * 100})
                        in_position = False
                    elif curr_row["low"] <= tp:
                        trades.append({**trade_features, "label": 0, "close_price": tp, "close_time": curr_time, "pnl": abs(entry_price - tp) * 100})
                        in_position = False
                        
                # Nếu lệnh đóng, chuyển trạng thái
                if not in_position:
                    continue

            # 2. Nếu chưa có lệnh, kiểm tra điều kiện vào lệnh của chiến lược gốc
            if not in_position:
                # Điều kiện BUY: RSI quá bán (< 35) + Giá đóng cửa vượt EMA20
                if prev_row["rsi"] < 35 and curr_row["close"] > curr_row["ema20"] and curr_row["atr"] > 0:
                    in_position = True
                    pos_type = "BUY"
                    entry_price = curr_row["close"]
                    entry_time = curr_time
                    atr_val = curr_row["atr"]
                    
                    sl = entry_price - (2.0 * atr_val)
                    tp = entry_price + (3.0 * atr_val)
                    
                    # Trích xuất đặc trưng tại thời điểm vào lệnh
                    ts = curr_time.timestamp()
                    trade_features = {
                        "entry_time": curr_time.isoformat(),
                        "symbol": self.symbol,
                        "action": "BUY",
                        "entry_price": entry_price,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "rsi": curr_row["rsi"],
                        "atr": atr_val,
                        "dist_ema200": curr_row["dist_ema200"],
                        "spread": curr_row["spread"],
                        "hour": curr_time.hour,
                        "day_of_week": curr_time.weekday(),
                        "mins_to_news": news_fetcher.get_minutes_to_next_major_news(ts)
                    }
                
                # Điều kiện SELL: RSI quá mua (> 65) + Giá đóng cửa cắt xuống dưới EMA20
                elif prev_row["rsi"] > 65 and curr_row["close"] < curr_row["ema20"] and curr_row["atr"] > 0:
                    in_position = True
                    pos_type = "SELL"
                    entry_price = curr_row["close"]
                    entry_time = curr_time
                    atr_val = curr_row["atr"]
                    
                    sl = entry_price + (2.0 * atr_val)
                    tp = entry_price - (3.0 * atr_val)
                    
                    # Trích xuất đặc trưng
                    ts = curr_time.timestamp()
                    trade_features = {
                        "entry_time": curr_time.isoformat(),
                        "symbol": self.symbol,
                        "action": "SELL",
                        "entry_price": entry_price,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "rsi": curr_row["rsi"],
                        "atr": atr_val,
                        "dist_ema200": curr_row["dist_ema200"],
                        "spread": curr_row["spread"],
                        "hour": curr_time.hour,
                        "day_of_week": curr_time.weekday(),
                        "mins_to_news": news_fetcher.get_minutes_to_next_major_news(ts)
                    }

        trades_df = pd.DataFrame(trades)
        logger.info(f"✅ Backtest hoàn tất. Tổng số lệnh thu được: {len(trades_df)}")
        if len(trades_df) > 0:
            win_rate = (trades_df["label"] == 0).sum() / len(trades_df) * 100
            logger.info(f"📊 Tỷ lệ Thắng ban đầu (chưa lọc): {win_rate:.2f}%")
        return trades_df

    def start(self, days: int = 180):
        """Khởi động toàn bộ luồng Backtest và lưu kết quả ra CSV"""
        df = self.generate_synthetic_data(days)
        df = self.calculate_indicators(df)
        trades_df = self.run_backtest(df)
        
        # Lưu file CSV làm dữ liệu cho AI
        trades_df.to_csv(BACKTEST_CSV, index=False)
        logger.info(f"💾 Đã lưu dữ liệu backtest làm dữ liệu huấn luyện AI tại: {BACKTEST_CSV}")
        return BACKTEST_CSV

if __name__ == "__main__":
    engine = BacktestEngine()
    engine.start(180)
