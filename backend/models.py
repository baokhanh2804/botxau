from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from backend.database import Base

class Strategy(Base):
    """Bảng quản lý chiến lược giao dịch"""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    risk_percent = Column(Float, default=1.0) # Tỷ lệ rủi ro riêng cho chiến lược này
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class TradeSignal(Base):
    """Lịch sử tất cả tín hiệu Webhook nhận được"""
    __tablename__ = "trade_signals"

    id = Column(Integer, primary_key=True, index=True)
    strategy_name = Column(String(100), index=True)
    symbol = Column(String(20), index=True) # VD: XAUUSD
    action = Column(String(10)) # BUY, SELL, CLOSE_ALL
    price = Column(Float)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    raw_payload = Column(Text) # Lưu toàn bộ chuỗi JSON thô để đối chiếu khi có lỗi
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ExecutedTrade(Base):
    """Danh sách các lệnh đã gửi lên sàn và trạng thái thực tế"""
    __tablename__ = "executed_trades"

    id = Column(Integer, primary_key=True, index=True)
    ticket = Column(Integer, unique=True, index=True, nullable=True) # Mã ticket MT5 trả về
    strategy_name = Column(String(100))
    symbol = Column(String(20))
    action = Column(String(10)) # BUY, SELL
    requested_volume = Column(Float) # Số lot đề xuất ban đầu
    actual_volume = Column(Float, nullable=True) # Số lot khớp thực tế sau khi AI lọc/giảm tải
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    
    # AI Filtering logs
    ai_decision = Column(String(20)) # ALLOWED, BLOCKED, HALF_SIZE
    ai_loss_probability = Column(Float, nullable=True) # Xác suất thua do AI tính
    
    # Status
    status = Column(String(20), default="PENDING") # PENDING, FILLED, REJECTED, CLOSED
    reject_reason = Column(String(255), nullable=True)
    pnl = Column(Float, default=0.0)
    
    open_time = Column(DateTime(timezone=True), server_default=func.now())
    close_time = Column(DateTime(timezone=True), nullable=True)

class DailyRiskStatus(Base):
    """Trạng thái kiểm soát rủi ro trong ngày để chặn cháy tài khoản"""
    __tablename__ = "daily_risk_status"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String(10), unique=True, index=True) # Định dạng YYYY-MM-DD
    start_balance = Column(Float) # Số dư đầu ngày
    highest_equity = Column(Float) # Equity cao nhất đạt được trong ngày
    lowest_equity = Column(Float) # Equity thấp nhất trong ngày
    is_blocked = Column(Boolean, default=False) # Bị khóa giao dịch hay không
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
