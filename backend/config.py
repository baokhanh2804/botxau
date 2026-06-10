import os
from pydantic_settings import BaseSettings
from pathlib import Path

# Thư mục gốc của Backend
BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    # Cấu hình Web Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SECRET_WEBHOOK_TOKEN: str = "super_secret_botxau_token"

    # Cấu hình Database (SQLite mặc định để dễ deploy chạy thử)
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/botxau.db"

    # Cấu hình MetaTrader 5
    MT5_MOCK: bool = True  # Mặc định bật MOCK để chạy thử không lỗi trên máy không có MT5
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""
    MT5_PATH: str = "" # Đường dẫn tới terminal64.exe của MT5 nếu cần thiết

    # Cấu hình Quản trị rủi ro (Risk Management)
    RISK_MAX_DAILY_DRAWDOWN_PCT: float = 5.0   # Tối đa âm 5% tài khoản một ngày
    RISK_MAX_TRADE_RISK_PCT: float = 1.0       # Tối đa rủi ro 1% tài khoản trên mỗi lệnh dựa vào SL
    RISK_DEFAULT_LOT_SIZE: float = 0.01        # Kích thước lot mặc định nếu không tính được lot động
    RISK_MAX_LOT_SIZE: float = 1.0             # Giới hạn kích thước lot lớn nhất để tránh lỗi ngón tay béo (fat-finger)
    RISK_MAX_OPEN_POSITIONS: int = 5           # Tối đa 5 vị thế mở cùng một lúc cho Vàng
    
    # Cấu hình Bộ lọc AI
    AI_FILTER_ENABLED: bool = True
    AI_LOSS_PROB_THRESHOLD: float = 0.60      # Nếu AI dự đoán khả năng thua > 60% thì chặn lệnh
    AI_HALF_SIZE_THRESHOLD: float = 0.45      # Nếu khả năng thua từ 45% -> 60%, giảm một nửa lot size

    class Config:
        env_file = f"{BASE_DIR}/.env"
        env_file_encoding = "utf-8"

settings = Settings()
