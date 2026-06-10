import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Body, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from backend.config import settings
from backend.database import engine, Base, get_db
from backend.models import Strategy, TradeSignal, ExecutedTrade, DailyRiskStatus
from backend.mt5_connector import mt5_connector
from backend.risk_manager import risk_manager
from ai_engine.news_fetcher import news_fetcher
from ai_engine.meta_labeler import meta_labeler
from ai_engine.backtest import BacktestEngine

# Cấu hình Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("botxau.main")

# Khởi tạo FastAPI App
app = FastAPI(
    title="BotXau API Gateway",
    description="Hệ thống giao dịch tự động tích hợp Bộ lọc rủi ro AI cho XAU/USD",
    version="1.0.0"
)

# Cấu hình CORS để Frontend gọi vào
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === PYDANTIC SCHEMAS ===
class SignalPayload(BaseModel):
    strategy_name: str = Field(..., example="RSI_EMA_Cross")
    symbol: str = Field("XAUUSD", example="XAUUSD")
    action: str = Field(..., example="BUY") # BUY, SELL, CLOSE_ALL
    price: float = Field(..., example=2350.50)
    stop_loss: Optional[float] = Field(None, example=2340.00)
    take_profit: Optional[float] = Field(None, example=2365.00)
    token: str = Field(..., example="super_secret_botxau_token")

class StrategyUpdate(BaseModel):
    is_active: bool
    risk_percent: float

# === EVENT STARTUP ===
@app.on_event("startup")
def startup_event():
    logger.info("🚀 Đang khởi động hệ thống BotXau...")
    
    # 1. Tạo cấu trúc DB nếu chưa có
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Đồng bộ Cơ sở dữ liệu hoàn thành.")
    
    # 2. Tạo các Chiến lược mặc định
    db = next(get_db())
    default_strategies = [
        {"name": "RSI_EMA_Cross", "description": "Chiến lược giao cắt RSI quá mua quá bán kết hợp EMA20"},
        {"name": "TradingView_Webhook", "description": "Nhận tín hiệu từ Webhook TradingView bên ngoài"},
        {"name": "Scalping_Gold", "description": "Chiến lược Scalping nhanh khung M1"}
    ]
    for s_info in default_strategies:
        exists = db.query(Strategy).filter(Strategy.name == s_info["name"]).first()
        if not exists:
            new_strat = Strategy(
                name=s_info["name"],
                description=s_info["description"],
                is_active=True,
                risk_percent=1.0
            )
            db.add(new_strat)
    db.commit()
    logger.info("✅ Tạo các chiến lược mặc định thành công.")

    # 3. Khởi tạo kết nối MT5
    connected = mt5_connector.initialize()
    if connected:
        logger.info("✅ Cầu nối MT5 Terminal sẵn sàng hoạt động.")
    else:
        logger.warning("⚠️ Cầu nối MT5 Terminal không sẵn sàng. Tự động chuyển sang Mock Mode.")

    # 4. Tự động kiểm tra và huấn luyện mô hình AI nếu chưa tồn tại
    from ai_engine.meta_labeler import MODEL_PATH
    if not MODEL_PATH.exists():
        logger.warning("⚠️ Không tìm thấy mô hình AI đã huấn luyện. Đang khởi chạy Backtest và tự động Train...")
        try:
            backtest_eng = BacktestEngine()
            csv_file = backtest_eng.start(days=120) # Chạy backtest 120 ngày tạo mẫu
            metrics = meta_labeler.train(str(csv_file))
            logger.info(f"🎉 Tự động huấn luyện mô hình AI thành công. Test Accuracy: {metrics['test_accuracy']*100:.2f}%")
        except Exception as e:
            logger.error(f"❌ Tự động huấn luyện mô hình AI thất bại: {str(e)}")

# === HELPER FUNCTIONS FOR INDICATORS ===
def calculate_indicators_realtime() -> Dict[str, float]:
    """Lấy dữ liệu nến lịch sử từ MT5 để tính toán các chỉ báo kỹ thuật realtime"""
    try:
        # Lấy 150 nến gần nhất trên khung M5 của Vàng
        rates = mt5_connector.get_historical_data("XAUUSD", "M5", 150)
        if not rates or len(rates) < 50:
            return {"rsi": 50.0, "atr": 2.50, "dist_ema200": 0.0}

        df = pd.DataFrame(rates)
        
        # 1. Tính EMA 200
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df["close"].ewm(span=len(df), adjust=False).mean()
        
        # 2. Tính RSI 14
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))

        # 3. Tính ATR 14
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(14).mean()

        last_row = df.iloc[-1]
        
        return {
            "rsi": float(last_row["rsi"]) if not np.isnan(last_row["rsi"]) else 50.0,
            "atr": float(last_row["atr"]) if not np.isnan(last_row["atr"]) else 2.50,
            "dist_ema200": float(last_row["close"] - last_row["ema200"]) if not np.isnan(last_row["ema200"]) else 0.0
        }
    except Exception as e:
        logger.error(f"❌ Không tính toán được chỉ báo chỉ số realtime: {str(e)}")
        return {"rsi": 50.0, "atr": 2.50, "dist_ema200": 0.0}

# === API ENDPOINTS ===

@app.post("/api/webhook", status_code=status.HTTP_201_CREATED)
def receive_webhook(payload: SignalPayload, db: Session = Depends(get_db)):
    """Đầu nhận Webhook tín hiệu giao dịch từ TradingView hoặc Bot ngoài"""
    # 1. Xác thực Token
    if payload.token != settings.SECRET_WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Webhook Token xác thực không hợp lệ.")

    logger.info(f"📥 Nhận tín hiệu Webhook: {payload.strategy_name} - {payload.action} {payload.symbol} tại {payload.price}")

    # 2. Ghi nhật ký tín hiệu thô vào cơ sở dữ liệu
    signal_log = TradeSignal(
        strategy_name=payload.strategy_name,
        symbol=payload.symbol.upper(),
        action=payload.action.upper(),
        price=payload.price,
        stop_loss=payload.stop_loss,
        take_profit=payload.take_profit,
        raw_payload=payload.json()
    )
    db.add(signal_log)
    db.commit()

    # 3. Kiểm tra xem chiến lược có được kích hoạt không
    strat = db.query(Strategy).filter(Strategy.name == payload.strategy_name).first()
    if not strat:
        raise HTTPException(status_code=400, detail=f"Chiến lược '{payload.strategy_name}' không tồn tại trong hệ thống.")
    if not strat.is_active:
        logger.info(f"🚫 Chiến lược {payload.strategy_name} đang bị TẮT. Bỏ qua tín hiệu.")
        return {"status": "IGNORED", "reason": "Chiến lược giao dịch đang bị Tắt"}

    # 4. Nếu action là CLOSE_ALL (Lệnh thoát khẩn cấp/chốt toàn bộ)
    if payload.action.upper() == "CLOSE_ALL":
        close_res = mt5_connector.close_all_positions()
        
        # Cập nhật trạng thái các vị thế trong DB thành CLOSED
        db.query(ExecutedTrade).filter(ExecutedTrade.status == "FILLED").update(
            {"status": "CLOSED", "close_time": datetime.now(timezone.utc)}
        )
        db.commit()
        return {"status": "CLOSED_SUCCESS", "detail": close_res}

    # 5. Lấy danh sách lệnh đang mở trên sàn để kiểm soát rủi ro
    open_positions = mt5_connector.get_open_positions()
    open_positions_count = len(open_positions)

    # 6. Kiểm tra các quy tắc Quản lý rủi ro (Risk Filter)
    risk_check = risk_manager.validate_new_signal(
        db=db,
        symbol=payload.symbol,
        action=payload.action,
        stop_loss=payload.stop_loss,
        open_positions_count=open_positions_count
    )

    if not risk_check["allowed"]:
        # Ghi nhận lệnh bị từ chối do quản lý rủi ro vào DB
        rejected_trade = ExecutedTrade(
            strategy_name=payload.strategy_name,
            symbol=payload.symbol.upper(),
            action=payload.action.upper(),
            requested_volume=settings.RISK_DEFAULT_LOT_SIZE,
            actual_volume=0.0,
            entry_price=payload.price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            ai_decision="REJECTED_BY_RISK",
            status="REJECTED",
            reject_reason=risk_check["reason"]
        )
        db.add(rejected_trade)
        db.commit()
        logger.warning(f"🚫 Tín hiệu bị TỪ CHỐI bởi Risk Manager: {risk_check['reason']}")
        return {"status": "REJECTED_BY_RISK", "reason": risk_check["reason"]}

    # 7. Tính toán các đặc trưng Realtime (Feature Store) phục vụ AI
    indicators = calculate_indicators_realtime()
    prices = mt5_connector.get_symbol_info(payload.symbol)
    spread = prices.get("spread", 15) if prices else 15
    
    current_time = datetime.now(timezone.utc)
    features = {
        "rsi": indicators["rsi"],
        "atr": indicators["atr"],
        "dist_ema200": indicators["dist_ema200"],
        "spread": spread,
        "hour": current_time.hour,
        "day_of_week": current_time.weekday(),
        "action_code": 0 if payload.action.upper() == "BUY" else 1,
        "mins_to_news": news_fetcher.get_minutes_to_next_major_news(current_time.timestamp())
    }

    # 8. Đẩy tín hiệu qua Bộ lọc AI (Loss-Filtering AI)
    loss_prob = meta_labeler.predict_loss_probability(features)
    ai_decision = "ALLOWED"
    
    if settings.AI_FILTER_ENABLED:
        if loss_prob >= settings.AI_LOSS_PROB_THRESHOLD:
            ai_decision = "BLOCKED"
        elif loss_prob >= settings.AI_HALF_SIZE_THRESHOLD:
            ai_decision = "HALF_SIZE"

    logger.info(f"🤖 Dự đoán AI: Khả năng lệnh bị THUA (SL): {loss_prob*100:.2f}%. Quyết định AI: {ai_decision}")

    if ai_decision == "BLOCKED":
        # Ghi nhận lệnh bị chặn bởi AI vào DB
        blocked_trade = ExecutedTrade(
            strategy_name=payload.strategy_name,
            symbol=payload.symbol.upper(),
            action=payload.action.upper(),
            requested_volume=settings.RISK_DEFAULT_LOT_SIZE,
            actual_volume=0.0,
            entry_price=payload.price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            ai_decision="BLOCKED",
            ai_loss_probability=loss_prob,
            status="BLOCKED_BY_AI",
            reject_reason=f"AI dự đoán xác suất thua cao ({loss_prob*100:.1f}%)"
        )
        db.add(blocked_trade)
        db.commit()
        logger.warning(f"🚫 Tín hiệu bị CHẶN bởi Bộ lọc AI (Xác suất thua: {loss_prob*100:.2f}%)")
        return {"status": "BLOCKED_BY_AI", "loss_probability": loss_prob}

    # 9. Tính toán khối lượng giao dịch (Lot size) tối ưu
    acc_info = mt5_connector.get_account_info()
    balance = acc_info.get("balance", 10000.0)
    
    calculated_lot = risk_manager.calculate_lot_size(
        balance=balance,
        entry_price=payload.price,
        stop_loss=payload.stop_loss
    )

    # Nếu AI khuyến nghị giảm khối lượng
    actual_lot = calculated_lot
    if ai_decision == "HALF_SIZE":
        actual_lot = round(calculated_lot / 2, 2)
        actual_lot = max(0.01, actual_lot) # Đảm bảo tối thiểu 0.01 lot
        logger.info(f"⚠️ Giảm 1/2 khối lượng lệnh do AI đề xuất: {calculated_lot} lot -> {actual_lot} lot.")

    # 10. Gửi lệnh giao dịch thực tế lên sàn qua MT5 API
    order_res = mt5_connector.send_order(
        symbol=payload.symbol,
        action=payload.action,
        volume=actual_lot,
        price=payload.price,
        stop_loss=payload.stop_loss,
        take_profit=payload.take_profit,
        comment=f"BotXau {ai_decision}"
    )

    if order_res["status"] == "SUCCESS":
        # Lưu thông tin lệnh đã khớp vào DB
        executed_trade = ExecutedTrade(
            ticket=order_res["ticket"],
            strategy_name=payload.strategy_name,
            symbol=payload.symbol.upper(),
            action=payload.action.upper(),
            requested_volume=calculated_lot,
            actual_volume=actual_lot,
            entry_price=order_res["price"],
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            ai_decision=ai_decision,
            ai_loss_probability=loss_prob,
            status="FILLED"
        )
        db.add(executed_trade)
        db.commit()
        return {"status": "SUCCESS", "ticket": order_res["ticket"], "lot_size": actual_lot, "price": order_res["price"]}
    else:
        # Lưu thông tin lệnh bị sàn từ chối
        failed_trade = ExecutedTrade(
            strategy_name=payload.strategy_name,
            symbol=payload.symbol.upper(),
            action=payload.action.upper(),
            requested_volume=calculated_lot,
            actual_volume=actual_lot,
            entry_price=payload.price,
            stop_loss=payload.stop_loss,
            take_profit=payload.take_profit,
            ai_decision=ai_decision,
            ai_loss_probability=loss_prob,
            status="FAILED",
            reject_reason=order_res.get("reason", "MT5 Terminal error")
        )
        db.add(failed_trade)
        db.commit()
        return {"status": "FAILED", "reason": order_res.get("reason")}

@app.get("/api/dashboard")
def get_dashboard_data(db: Session = Depends(get_db)):
    """Trả về toàn bộ thông tin tài khoản, vị thế mở và nhật ký giao dịch cho Dashboard"""
    # 1. Trạng thái tài khoản
    acc = mt5_connector.get_account_info()
    
    # 2. Vị thế mở hiện tại
    open_positions = mt5_connector.get_open_positions()

    # 3. Trạng thái Drawdown ngày
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    risk_status = db.query(DailyRiskStatus).filter(DailyRiskStatus.date == today_str).first()
    drawdown_pct = 0.0
    is_blocked = False
    
    if risk_status and acc:
        drawdown_pct = ((risk_status.highest_equity - acc["equity"]) / risk_status.highest_equity) * 100 if risk_status.highest_equity > 0 else 0.0
        is_blocked = risk_status.is_blocked

    # 4. Danh sách các chiến lược
    strategies = db.query(Strategy).all()

    # 5. Nhật ký lệnh thực tế (Executed) & Tín hiệu Webhook gần nhất
    recent_executed = db.query(ExecutedTrade).order_by(ExecutedTrade.open_time.desc()).limit(20).all()
    recent_signals = db.query(TradeSignal).order_by(TradeSignal.created_at.desc()).limit(20).all()

    # 6. Đánh giá trạng thái huấn luyện AI hiện tại
    ai_status = "NOT_TRAINED"
    feature_importance = {}
    if meta_labeler.model is not None:
        ai_status = "READY"
        try:
            # Lấy feature importance từ mô hình
            importances = meta_labeler.model.feature_importances_
            feature_importance = {feat: float(imp) for feat, imp in zip(meta_labeler.features, importances)}
        except Exception:
            pass

    return {
        "account": acc,
        "open_positions": open_positions,
        "daily_risk": {
            "drawdown_percent": max(0.0, drawdown_pct),
            "max_drawdown_limit": settings.RISK_MAX_DAILY_DRAWDOWN_PCT,
            "is_blocked": is_blocked
        },
        "ai_settings": {
            "enabled": settings.AI_FILTER_ENABLED,
            "loss_prob_threshold": settings.AI_LOSS_PROB_THRESHOLD,
            "half_size_threshold": settings.AI_HALF_SIZE_THRESHOLD,
            "status": ai_status,
            "feature_importance": feature_importance
        },
        "strategies": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "is_active": s.is_active,
                "risk_percent": s.risk_percent
            } for s in strategies
        ],
        "recent_trades": [
            {
                "id": t.id,
                "ticket": t.ticket,
                "strategy_name": t.strategy_name,
                "symbol": t.symbol,
                "action": t.action,
                "actual_volume": t.actual_volume,
                "entry_price": t.entry_price,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "ai_decision": t.ai_decision,
                "ai_loss_probability": t.ai_loss_probability,
                "status": t.status,
                "pnl": t.pnl,
                "reject_reason": t.reject_reason,
                "open_time": t.open_time.isoformat() if t.open_time else None
            } for t in recent_executed
        ],
        "recent_signals": [
            {
                "id": s.id,
                "strategy_name": s.strategy_name,
                "symbol": s.symbol,
                "action": s.action,
                "price": s.price,
                "stop_loss": s.stop_loss,
                "take_profit": s.take_profit,
                "created_at": s.created_at.isoformat() if s.created_at else None
            } for s in recent_signals
        ]
    }

@app.post("/api/panic")
def panic_button(db: Session = Depends(get_db)):
    """Panic Button: Đóng ngay lập tức toàn bộ lệnh mở và cập nhật trạng thái trong cơ sở dữ liệu"""
    logger.warning("🚨 PANIC BUTTON KÍCH HOẠT! ĐÓNG TẤT CẢ CÁC LỆNH ĐANG MỞ...")
    close_res = mt5_connector.close_all_positions()
    
    # Cập nhật DB
    db.query(ExecutedTrade).filter(ExecutedTrade.status == "FILLED").update(
        {"status": "CLOSED", "close_time": datetime.now(timezone.utc)}
    )
    db.commit()
    return {"status": "PANIC_SUCCESS", "detail": close_res}

@app.post("/api/strategies/{strategy_id}")
def update_strategy(strategy_id: int, payload: StrategyUpdate, db: Session = Depends(get_db)):
    """Cập nhật cài đặt bật/tắt và tỷ lệ rủi ro của chiến lược"""
    strat = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strat:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến lược giao dịch.")
    
    strat.is_active = payload.is_active
    strat.risk_percent = payload.risk_percent
    db.commit()
    logger.info(f"🔧 Đã cập nhật chiến lược {strat.name}: Active={payload.is_active}, Risk={payload.risk_percent}%")
    return {"status": "SUCCESS", "detail": "Cập nhật chiến lược thành công"}

@app.post("/api/ai/train")
def train_ai_model(days: int = Body(180, embed=True), db: Session = Depends(get_db)):
    """Yêu cầu chạy lại Backtest và huấn luyện/cập nhật lại mô hình AI Bộ lọc"""
    try:
        backtest_eng = BacktestEngine()
        csv_file = backtest_eng.start(days=days)
        metrics = meta_labeler.train(str(csv_file))
        return {
            "status": "SUCCESS",
            "message": "Huấn luyện lại mô hình AI thành công",
            "metrics": metrics
        }
    except Exception as e:
        logger.error(f"❌ Huấn luyện lại AI thất bại: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi train mô hình: {str(e)}")

@app.post("/api/settings/ai-toggle")
def toggle_ai_filter(enabled: bool = Body(..., embed=True)):
    """Bật hoặc Tắt tính năng lọc lệnh của AI"""
    settings.AI_FILTER_ENABLED = enabled
    logger.info(f"🔧 Cấu hình AI Filter set thành: {enabled}")
    return {"status": "SUCCESS", "ai_filter_enabled": enabled}

if __name__ == "__main__":
    import uvicorn
    # Khởi chạy cục bộ
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
