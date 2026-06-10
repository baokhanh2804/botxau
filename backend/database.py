from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# Khởi tạo Engine. 
# Với SQLite, cần thiết lập check_same_thread=False vì FastAPI xử lý đa luồng bất đồng bộ.
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL, 
    connect_args=connect_args,
    echo=False # Đặt thành True nếu muốn xem log các câu lệnh SQL
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency cung cấp Database Session cho FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
