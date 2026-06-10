import logging
from datetime import date
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import DailyRiskStatus
from backend.mt5_connector import mt5_connector

logger = logging.getLogger("botxau.risk")

class RiskManager:
    @staticmethod
    def get_or_create_daily_status(db: Session, balance: float, equity: float) -> DailyRiskStatus:
        """Lấy hoặc tạo mới bản ghi trạng thái rủi ro của ngày hôm nay"""
        today_str = date.today().isoformat()
        status = db.query(DailyRiskStatus).filter(DailyRiskStatus.date == today_str).first()
        
        if not status:
            status = DailyRiskStatus(
                date=today_str,
                start_balance=balance,
                highest_equity=max(balance, equity),
                lowest_equity=min(balance, equity),
                is_blocked=False
            )
            db.add(status)
            db.commit()
            db.refresh(status)
            logger.info(f"📅 Khởi tạo ngày giao dịch mới: {today_str}. Balance đầu ngày: {balance}$")
        
        return status

    @classmethod
    def check_daily_drawdown(cls, db: Session) -> tuple[bool, float]:
        """
        Kiểm tra tỷ lệ sụt giảm tài sản (Drawdown) trong ngày.
        Nếu sụt giảm vượt quá giới hạn cho phép, tự động đóng toàn bộ lệnh và khóa tài khoản.
        """
        # Lấy thông tin tài khoản realtime từ MT5
        acc = mt5_connector.get_account_info()
        if not acc:
            logger.error("❌ Không lấy được thông tin tài khoản để kiểm tra drawdown.")
            return False, 0.0

        balance = acc["balance"]
        equity = acc["equity"]

        status = cls.get_or_create_daily_status(db, balance, equity)
        
        # Nếu tài khoản đã bị chặn từ trước
        if status.is_blocked:
            return True, ((status.highest_equity - equity) / status.highest_equity * 100)

        # Cập nhật High/Low Equity trong ngày
        updated = False
        if equity > status.highest_equity:
            status.highest_equity = equity
            updated = True
        if equity < status.lowest_equity:
            status.lowest_equity = equity
            updated = True

        if updated:
            db.commit()
            db.refresh(status)

        # Tính toán Drawdown dựa trên đỉnh Equity cao nhất trong ngày
        drawdown_val = status.highest_equity - equity
        drawdown_pct = (drawdown_val / status.highest_equity) * 100 if status.highest_equity > 0 else 0.0

        # Nếu Drawdown vượt quá giới hạn tối đa
        if drawdown_pct >= settings.RISK_MAX_DAILY_DRAWDOWN_PCT:
            status.is_blocked = True
            db.commit()
            logger.error(f"🚨 VI PHẠM DRAWDOWN NGÀY! Drawdown hiện tại: {drawdown_pct:.2f}% (Giới hạn: {settings.RISK_MAX_DAILY_DRAWDOWN_PCT}%).")
            
            # Kích hoạt Panic Button để đóng mọi vị thế mở ngay lập tức
            close_res = mt5_connector.close_all_positions()
            logger.warning(f"🚨 Tự động đóng toàn bộ lệnh: Đã đóng {close_res.get('closed_count', 0)} lệnh.")
            return True, drawdown_pct

        return False, drawdown_pct

    @staticmethod
    def calculate_lot_size(balance: float, entry_price: float, stop_loss: float) -> float:
        """
        Tính toán Lot Size động dựa trên khoảng cách SL để khống chế rủi ro cố định (VD: 1% tài khoản).
        Công thức: Risk_Amount = Balance * Risk_Percent
                  Points_To_SL = abs(Entry_Price - Stop_Loss)
                  Risk_Per_Lot = Points_To_SL * Contract_Size (1 Lot Vàng = 100 Ounces)
                  Lot_Size = Risk_Amount / Risk_Per_Lot
        """
        if not stop_loss or entry_price == stop_loss:
            return settings.RISK_DEFAULT_LOT_SIZE

        # Số tiền tối đa chấp nhận mất trên lệnh này
        risk_amount = balance * (settings.RISK_MAX_TRADE_RISK_PCT / 100.0)
        
        # Khoảng cách giá đến SL (đơn vị $)
        price_distance = abs(entry_price - stop_loss)
        
        # 1 Lot XAUUSD tương đương 100 Ounces. 
        # Nếu Vàng di chuyển 1 USD, 1 Lot sẽ lãi/lỗ 100 USD.
        multiplier = 100.0 
        risk_per_lot = price_distance * multiplier

        if risk_per_lot <= 0:
            return settings.RISK_DEFAULT_LOT_SIZE

        calculated_lot = risk_amount / risk_per_lot

        # Giới hạn kích thước Lot trong khoảng an toàn [0.01, RISK_MAX_LOT_SIZE]
        final_lot = max(0.01, min(calculated_lot, settings.RISK_MAX_LOT_SIZE))
        
        # Làm tròn về 2 chữ số thập phân (chuẩn Lot của MT5)
        return round(final_lot, 2)

    @classmethod
    def validate_new_signal(cls, db: Session, symbol: str, action: str, stop_loss: float, 
                             open_positions_count: int) -> dict:
        """Kiểm nghiệm toàn diện xem tín hiệu mới có thỏa mãn điều kiện rủi ro để vào lệnh hay không"""
        symbol = symbol.upper()
        action = action.upper()

        # 1. Kiểm tra Daily Drawdown
        is_blocked, current_dd = cls.check_daily_drawdown(db)
        if is_blocked:
            return {
                "allowed": False,
                "reason": f"Tài khoản đang bị khóa do vi phạm Drawdown ngày ({current_dd:.2f}%)"
            }

        # Nếu là lệnh đóng vị thế thì luôn cho phép
        if action == "CLOSE_ALL":
            return {"allowed": True, "reason": "Lệnh đóng trạng thái luôn được phép"}

        # 2. Kiểm tra giới hạn số lượng vị thế mở tối đa
        if open_positions_count >= settings.RISK_MAX_OPEN_POSITIONS:
            return {
                "allowed": False,
                "reason": f"Vượt quá số lượng lệnh mở tối đa cho phép ({open_positions_count}/{settings.RISK_MAX_OPEN_POSITIONS})"
            }

        # 3. Yêu cầu bắt buộc phải có Stop Loss khi mở vị thế mới để AI tính toán đặc trưng
        if not stop_loss:
            return {
                "allowed": False,
                "reason": "Lệnh mở vị thế mới bắt buộc phải đi kèm mức dừng lỗ (Stop Loss)"
            }

        return {"allowed": True, "reason": "Thỏa mãn tất cả các bộ lọc Quản lý vốn"}

risk_manager = RiskManager()
