import sys
import time
import logging
import random
from datetime import datetime
from backend.config import settings

logger = logging.getLogger("botxau.mt5")
logging.basicConfig(level=logging.INFO)

# Biến toàn cục để lưu trữ trạng thái kết nối
MT5_AVAILABLE = False
mt5 = None

# Cố gắng import thư viện MetaTrader5 nếu đang chạy trên Windows
if sys.platform == "win32":
    try:
        import MetaTrader5 as mt5_lib
        mt5 = mt5_lib
        MT5_AVAILABLE = True
    except ImportError:
        logger.warning("Thư viện 'MetaTrader5' chưa được cài đặt. Hệ thống sẽ tự động chuyển sang chế độ Mock.")

# Giả lập Trạng thái Tài khoản Mock
mock_account = {
    "balance": 10000.0,
    "equity": 10000.0,
    "profit": 0.0,
    "margin": 0.0,
    "margin_free": 10000.0,
    "lever": 500,
    "currency": "USD",
    "name": "BotXau Mock Account"
}

# Giả lập các Vị thế (Positions) Mock
# Cấu trúc: { ticket: {ticket, symbol, type, volume, open_price, sl, tp, pnl, time} }
mock_positions = {}
mock_ticket_counter = 10000000

class MT5Connector:
    def __init__(self):
        self.is_connected = False
        self.mock_mode = settings.MT5_MOCK or not MT5_AVAILABLE
        if self.mock_mode:
            logger.info("🔧 Đang chạy MT5 ở chế độ GIẢ LẬP (MOCK MODE).")
        else:
            logger.info("🔌 Đang chạy MT5 ở chế độ KẾT NỐI SÀN THỰC.")

    def initialize(self) -> bool:
        """Khởi tạo kết nối với MT5 Terminal"""
        if self.mock_mode:
            self.is_connected = True
            logger.info("✅ Giả lập kết nối MT5 thành công.")
            return True

        try:
            # Nếu có đường dẫn tùy chỉnh thì truyền vào path
            init_params = {}
            if settings.MT5_PATH:
                init_params["path"] = settings.MT5_PATH
                
            if not mt5.initialize(**init_params):
                logger.error(f"❌ Khởi động MT5 thất bại, mã lỗi: {mt5.last_error()}")
                return False

            # Đăng nhập nếu có thông tin tài khoản
            if settings.MT5_LOGIN > 0:
                authorized = mt5.login(
                    login=settings.MT5_LOGIN,
                    password=settings.MT5_PASSWORD,
                    server=settings.MT5_SERVER
                )
                if not authorized:
                    logger.error(f"❌ Đăng nhập tài khoản MT5 #{settings.MT5_LOGIN} thất bại: {mt5.last_error()}")
                    mt5.shutdown()
                    return False
                logger.info(f"✅ Đăng nhập thành công tài khoản MT5 #{settings.MT5_LOGIN}")

            self.is_connected = True
            logger.info("✅ Kết nối MT5 Terminal thành công.")
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi ngoại lệ khi khởi tạo MT5: {str(e)}")
            self.is_connected = False
            return False

    def shutdown(self):
        """Đóng kết nối MT5"""
        if not self.mock_mode and mt5:
            mt5.shutdown()
        self.is_connected = False
        logger.info("🔌 Đã ngắt kết nối với MT5.")

    def get_account_info(self) -> dict:
        """Lấy thông tin tài khoản hiện tại (Balance, Equity, Profit, Margin)"""
        global mock_account
        if self.mock_mode:
            # Cập nhật Equity dựa trên các vị thế giả lập đang mở
            open_pnl = sum(pos["pnl"] for pos in mock_positions.values())
            mock_account["profit"] = open_pnl
            mock_account["equity"] = mock_account["balance"] + open_pnl
            mock_account["margin"] = sum(pos["volume"] * 200 for pos in mock_positions.values()) # Giả lập margin 200$ mỗi lot
            mock_account["margin_free"] = mock_account["equity"] - mock_account["margin"]
            return mock_account.copy()

        if not self.is_connected and not self.initialize():
            return {}

        account = mt5.account_info()
        if account is None:
            logger.error(f"❌ Không lấy được thông tin tài khoản, lỗi: {mt5.last_error()}")
            return {}

        return {
            "balance": account.balance,
            "equity": account.equity,
            "profit": account.profit,
            "margin": account.margin,
            "margin_free": account.margin_free,
            "lever": account.leverage,
            "currency": account.currency,
            "name": account.name
        }

    def get_symbol_info(self, symbol: str) -> dict:
        """Lấy giá Bid, Ask, Spread của Symbol hiện tại"""
        # Chuẩn hóa tên Vàng trên sàn (XAUUSD hoặc GOLD)
        symbol = symbol.upper()
        
        if self.mock_mode:
            # Giả lập giá chạy quanh vùng 2300 - 2400
            # Lưu trữ giá cơ sở trong class hoặc dùng biến random
            base_price = getattr(self, "_mock_gold_price", 2350.0)
            change = random.uniform(-0.5, 0.5)
            base_price = max(1000.0, base_price + change)
            self._mock_gold_price = base_price
            
            spread_pips = random.uniform(1.2, 2.5) # Spread từ 12 đến 25 pips (1.2 -> 2.5$)
            bid = base_price
            ask = base_price + spread_pips
            return {
                "bid": bid,
                "ask": ask,
                "spread": int(spread_pips * 10), # pips * 10 = points
                "point": 0.01,
                "digits": 2
            }

        if not self.is_connected and not self.initialize():
            return {}

        # Kiểm tra sự tồn tại của symbol trong MarketWatch
        selected = mt5.symbol_select(symbol, True)
        if not selected:
            logger.error(f"❌ Không chọn được symbol {symbol} trong MarketWatch.")
            return {}

        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"❌ Không lấy được thông tin symbol {symbol}, lỗi: {mt5.last_error()}")
            return {}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            bid = info.bid
            ask = info.ask
        else:
            bid = tick.bid
            ask = tick.ask

        return {
            "bid": bid,
            "ask": ask,
            "spread": info.spread, # points
            "point": info.point,
            "digits": info.digits
        }

    def send_order(self, symbol: str, action: str, volume: float, price: float = 0.0, 
                   stop_loss: float = None, take_profit: float = None, comment: str = "") -> dict:
        """Gửi lệnh Market Buy hoặc Sell sang sàn"""
        global mock_ticket_counter, mock_positions, mock_account
        symbol = symbol.upper()
        action = action.upper()

        if action not in ["BUY", "SELL"]:
            return {"status": "FAILED", "reason": f"Hành động không hợp lệ: {action}"}

        # Lấy giá bid/ask hiện tại
        prices = self.get_symbol_info(symbol)
        if not prices:
            return {"status": "FAILED", "reason": "Không lấy được giá thị trường hiện tại"}

        # Xác định giá khớp lệnh (Buy khớp ở Ask, Sell khớp ở Bid)
        execution_price = prices["ask"] if action == "BUY" else prices["bid"]

        if self.mock_mode:
            mock_ticket_counter += 1
            ticket = mock_ticket_counter
            
            # Lưu vào danh sách các vị thế đang mở
            mock_positions[ticket] = {
                "ticket": ticket,
                "symbol": symbol,
                "type": action,
                "volume": volume,
                "open_price": execution_price,
                "sl": stop_loss,
                "tp": take_profit,
                "pnl": 0.0,
                "comment": comment,
                "time": datetime.now().isoformat()
            }
            logger.info(f"📈 [Mock Executed] Khớp lệnh {action} {volume} lot {symbol} tại {execution_price}. Ticket: {ticket}")
            return {
                "status": "SUCCESS",
                "ticket": ticket,
                "price": execution_price,
                "volume": volume
            }

        if not self.is_connected and not self.initialize():
            return {"status": "FAILED", "reason": "Mất kết nối với MT5 Terminal"}

        # Ánh xạ action sang MT5 Constants
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": float(execution_price),
            "deviation": 20, # Độ trượt tối đa cho phép (20 points)
            "magic": 999999, # Magic number định danh BotXau
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC, # Immediate or Cancel
        }

        if stop_loss is not None:
            request["sl"] = float(stop_loss)
        if take_profit is not None:
            request["tp"] = float(take_profit)

        result = mt5.order_send(request)
        if result is None:
            return {"status": "FAILED", "reason": f"Không có phản hồi từ MT5. Lỗi: {mt5.last_error()}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"❌ Gửi lệnh thất bại, mã lỗi retcode: {result.retcode}. Chi tiết: {result.comment}")
            return {"status": "FAILED", "reason": f"Sàn từ chối lệnh. Mã: {result.retcode}, Chi tiết: {result.comment}"}

        logger.info(f"🚀 [MT5 Executed] Khớp lệnh {action} {volume} lot {symbol} thành công. Ticket: {result.order}")
        return {
            "status": "SUCCESS",
            "ticket": result.order,
            "price": result.price,
            "volume": result.volume
        }

    def close_position(self, ticket: int) -> dict:
        """Đóng một vị thế giao dịch đang mở dựa theo ticket"""
        global mock_positions, mock_account
        
        if self.mock_mode:
            if ticket not in mock_positions:
                return {"status": "FAILED", "reason": f"Không tìm thấy ticket {ticket} để đóng"}
            
            pos = mock_positions.pop(ticket)
            prices = self.get_symbol_info(pos["symbol"])
            close_price = prices["bid"] if pos["type"] == "BUY" else prices["ask"]
            
            # Tính toán PnL cuối cùng của lệnh
            multiplier = 100.0 # Standard contract size của Gold là 100 ounces
            if pos["type"] == "BUY":
                pnl = (close_price - pos["open_price"]) * pos["volume"] * multiplier
            else:
                pnl = (pos["open_price"] - close_price) * pos["volume"] * multiplier
                
            mock_account["balance"] += pnl
            logger.info(f"📉 [Mock Closed] Đã đóng ticket {ticket}. PnL: {pnl:.2f}$. Balance mới: {mock_account['balance']:.2f}$")
            return {"status": "SUCCESS", "pnl": pnl, "close_price": close_price}

        if not self.is_connected and not self.initialize():
            return {"status": "FAILED", "reason": "Mất kết nối với MT5 Terminal"}

        # Lấy thông tin position từ MT5
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            return {"status": "FAILED", "reason": f"Không tìm thấy vị thế mở với ticket {ticket}"}

        position = positions[0]
        symbol = position.symbol
        volume = position.volume
        pos_type = position.type # 0 là BUY, 1 là SELL

        # Xác định chiều ngược lại để đóng lệnh
        close_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        prices = self.get_symbol_info(symbol)
        close_price = prices["bid"] if pos_type == mt5.ORDER_TYPE_BUY else prices["ask"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": close_type,
            "position": ticket,
            "price": float(close_price),
            "deviation": 20,
            "magic": 999999,
            "comment": f"Close Ticket {ticket}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"status": "FAILED", "reason": "Không nhận được phản hồi đóng lệnh từ MT5"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"status": "FAILED", "reason": f"Đóng lệnh thất bại. Mã: {result.retcode}, Chi tiết: {result.comment}"}

        logger.info(f"✅ [MT5 Closed] Đóng thành công ticket {ticket} tại giá {result.price}")
        return {"status": "SUCCESS", "pnl": result.profit, "close_price": result.price}

    def get_open_positions(self) -> list:
        """Lấy tất cả các vị thế đang mở"""
        if self.mock_mode:
            # Tính toán PnL tạm tính realtime cho từng vị thế mock
            updated_positions = []
            prices = self.get_symbol_info("XAUUSD")
            current_price = prices["bid"] # Dùng bid tạm tính
            multiplier = 100.0
            
            for ticket, pos in mock_positions.items():
                p = pos.copy()
                # Tính toán PnL tạm tính
                if p["type"] == "BUY":
                    p["pnl"] = (prices["bid"] - p["open_price"]) * p["volume"] * multiplier
                else:
                    p["pnl"] = (p["open_price"] - prices["ask"]) * p["volume"] * multiplier
                # Gán lại vào mock_positions để lưu trữ
                mock_positions[ticket]["pnl"] = p["pnl"]
                updated_positions.append(p)
            return updated_positions

        if not self.is_connected and not self.initialize():
            return []

        positions = mt5.positions_get(symbol="XAUUSD")
        if positions is None:
            return []

        res = []
        for pos in positions:
            res.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                "volume": pos.volume,
                "open_price": pos.price_open,
                "sl": pos.sl,
                "tp": pos.tp,
                "pnl": pos.profit,
                "comment": pos.comment,
                "time": datetime.fromtimestamp(pos.time).isoformat()
            })
        return res

    def close_all_positions(self) -> dict:
        """Panic Button: Đóng toàn bộ các vị thế đang mở ngay lập tức"""
        logger.warning("🚨 [PANIC BUTTON] ĐANG ĐÓNG TOÀN BỘ CÁC VỊ THẾ GIAO DỊCH!")
        
        if self.mock_mode:
            tickets = list(mock_positions.keys())
            closed_count = 0
            total_pnl = 0.0
            for ticket in tickets:
                res = self.close_position(ticket)
                if res["status"] == "SUCCESS":
                    closed_count += 1
                    total_pnl += res.get("pnl", 0.0)
            return {"status": "SUCCESS", "closed_count": closed_count, "total_pnl": total_pnl}

        # Live Mode
        open_positions = mt5.positions_get()
        if open_positions is None or len(open_positions) == 0:
            return {"status": "SUCCESS", "closed_count": 0, "total_pnl": 0.0}

        closed_count = 0
        total_pnl = 0.0
        for pos in open_positions:
            res = self.close_position(pos.ticket)
            if res["status"] == "SUCCESS":
                closed_count += 1
                total_pnl += res.get("pnl", 0.0)
                
        return {"status": "SUCCESS", "closed_count": closed_count, "total_pnl": total_pnl}

    def get_historical_data(self, symbol: str, timeframe: str, count: int) -> list:
        """Lấy dữ liệu nến lịch sử từ sàn để tính toán chỉ báo kỹ thuật"""
        symbol = symbol.upper()
        
        # Ánh xạ timeframe sang MT5 Constants
        tf_mapping = {
            "M1": 1, "M5": 5, "M15": 15, "M30": 30,
            "H1": 16385, "H4": 16388, "D1": 16400
        }
        
        if self.mock_mode:
            # Tạo dữ liệu giả lập cho nến
            res = []
            base_price = 2350.0
            curr_time = time.time() - (count * 60 if timeframe == "M1" else count * 300)
            for i in range(count):
                open_p = base_price + random.uniform(-2, 2)
                close_p = open_p + random.uniform(-1.5, 1.5)
                high_p = max(open_p, close_p) + random.uniform(0, 1.5)
                low_p = min(open_p, close_p) - random.uniform(0, 1.5)
                base_price = close_p
                res.append({
                    "time": int(curr_time),
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "tick_volume": random.randint(100, 500)
                })
                curr_time += 60 if timeframe == "M1" else 300
            return res

        if not self.is_connected and not self.initialize():
            return []

        # Convert timeframe string to MT5 timeframe object
        mt5_tf = mt5.TIMEFRAME_M1
        if timeframe == "M5":
            mt5_tf = mt5.TIMEFRAME_M5
        elif timeframe == "M15":
            mt5_tf = mt5.TIMEFRAME_M15
        elif timeframe == "M30":
            mt5_tf = mt5.TIMEFRAME_M30
        elif timeframe == "H1":
            mt5_tf = mt5.TIMEFRAME_H1
        elif timeframe == "H4":
            mt5_tf = mt5.TIMEFRAME_H4
        elif timeframe == "D1":
            mt5_tf = mt5.TIMEFRAME_D1

        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None:
            logger.error(f"❌ Không lấy được dữ liệu nến lịch sử cho {symbol}, lỗi: {mt5.last_error()}")
            return []

        res = []
        for rate in rates:
            res.append({
                "time": int(rate[0]),
                "open": float(rate[1]),
                "high": float(rate[2]),
                "low": float(rate[3]),
                "close": float(rate[4]),
                "tick_volume": int(rate[5])
            })
        return res

# Khởi tạo instance kết nối duy nhất (singleton)
mt5_connector = MT5Connector()
