import os
import logging
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score
from xgboost import XGBClassifier

logger = logging.getLogger("botxau.ai")
logging.basicConfig(level=logging.INFO)

AI_DIR = Path(__file__).resolve().parent
MODEL_PATH = AI_DIR / "models" / "meta_labeler_model.joblib"
os.makedirs(AI_DIR / "models", exist_ok=True)

class MetaLabeler:
    """Hệ thống huấn luyện và suy luận AI Bộ lọc lệnh thua (Meta-Labeling)"""
    
    def __init__(self):
        self.model = None
        self.features = ["rsi", "atr", "dist_ema200", "spread", "hour", "day_of_week", "mins_to_news", "action_code"]
        self.load_model()

    def load_model(self):
        """Tải mô hình AI đã lưu nếu có"""
        if MODEL_PATH.exists():
            try:
                self.model = joblib.load(MODEL_PATH)
                logger.info(f"🤖 Đã tải thành công mô hình AI từ: {MODEL_PATH}")
            except Exception as e:
                logger.error(f"❌ Lỗi khi tải mô hình AI: {str(e)}")

    def preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Chuẩn hóa dữ liệu thô phục vụ huấn luyện và dự đoán"""
        processed_df = df.copy()
        
        # Ánh xạ action BUY -> 0, SELL -> 1
        if "action" in processed_df.columns:
            processed_df["action_code"] = processed_df["action"].map({"BUY": 0, "SELL": 1})
        elif "action_code" not in processed_df.columns:
            # Fallback nếu truyền thẳng action_code
            processed_df["action_code"] = 0
            
        # Đảm bảo điền đầy đủ giá trị rỗng
        processed_df.fillna(0, inplace=True)
        return processed_df

    def train(self, csv_path: str) -> dict:
        """
        Huấn luyện mô hình XGBoost dựa trên dữ liệu lịch sử từ Backtest.
        Target label = 1 (Lệnh chạm SL/Thua), 0 (Lệnh chạm TP/Thắng).
        """
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Không tìm thấy file dữ liệu backtest tại {csv_path}")

        logger.info(f"📊 Đang đọc dữ liệu từ {csv_path} để huấn luyện AI...")
        df_raw = pd.read_csv(csv_path)
        
        if len(df_raw) < 50:
            raise ValueError("Dữ liệu quá ít (cần ít nhất 50 lệnh) để huấn luyện mô hình AI.")

        df = self.preprocess_data(df_raw)
        
        X = df[self.features]
        y = df["label"] # 1: Thua, 0: Thắng

        # Phân tách dữ liệu Train/Test theo trình tự thời gian (ngăn ngừa Look-ahead bias)
        # Sử dụng 80% đầu để train, 20% cuối để kiểm nghiệm
        split_idx = int(len(df) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        logger.info(f"🏋️ Đang huấn luyện XGBoost Classifier... (Train size: {len(X_train)}, Test size: {len(X_test)})")
        
        # Cấu hình XGBoost tối ưu chống quá khớp (Overfitting)
        self.model = XGBClassifier(
            max_depth=3,
            learning_rate=0.05,
            n_estimators=100,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            eval_metric="logloss",
            random_state=42
        )
        
        self.model.fit(X_train, y_train)

        # Đánh giá mô hình trên tập Test
        y_pred = self.model.predict(X_test)
        y_pred_proba = self.model.predict_proba(X_test)[:, 1] # Xác suất Thua (Label 1)

        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)

        logger.info(f"✅ Huấn luyện hoàn tất. Đánh giá trên tập test:")
        logger.info(f"   - Accuracy: {accuracy*100:.2f}%")
        logger.info(f"   - Precision (Khả năng phát hiện đúng lệnh thua): {precision*100:.2f}%")
        logger.info(f"   - Recall (Tỷ lệ lệnh thua thực tế bị tóm gọn): {recall*100:.2f}%")

        # Lưu mô hình xuống đĩa
        joblib.dump(self.model, MODEL_PATH)
        logger.info(f"💾 Đã lưu mô hình AI tại: {MODEL_PATH}")

        # Tính toán hiệu quả cải thiện Win Rate sau khi áp dụng bộ lọc AI
        # Giả định bộ lọc AI chặn tất cả các lệnh có xác suất thua > 60%
        test_df = df_raw.iloc[split_idx:].copy()
        test_df["ai_loss_prob"] = y_pred_proba
        
        # Trước khi lọc
        total_trades = len(test_df)
        wins_before = (test_df["label"] == 0).sum()
        win_rate_before = (wins_before / total_trades) * 100 if total_trades > 0 else 0.0
        
        # Sau khi lọc (Chặn các lệnh có xác suất thua >= 60%)
        filtered_df = test_df[test_df["ai_loss_prob"] < 0.60]
        total_trades_after = len(filtered_df)
        wins_after = (filtered_df["label"] == 0).sum()
        win_rate_after = (wins_after / total_trades_after) * 100 if total_trades_after > 0 else 0.0
        blocked_count = total_trades - total_trades_after

        logger.info(f"📈 Phân tích hiệu quả Bộ lọc AI (Meta-Labeling):")
        logger.info(f"   - Số lệnh gốc: {total_trades} | Tỷ lệ Win Rate: {win_rate_before:.2f}%")
        logger.info(f"   - Số lệnh bị AI chặn: {blocked_count} ({blocked_count/total_trades*100:.1f}%)")
        logger.info(f"   - Số lệnh được thông qua: {total_trades_after} | Tỷ lệ Win Rate sau lọc: {win_rate_after:.2f}%")
        logger.info(f"   - Tăng trưởng tỷ lệ thắng: +{(win_rate_after - win_rate_before):.2f}%")

        # Thu thập độ quan trọng của đặc trưng (Feature Importance)
        importances = self.model.feature_importances_
        feature_importance_dict = {feat: float(imp) for feat, imp in zip(self.features, importances)}
        
        return {
            "test_accuracy": float(accuracy),
            "test_precision": float(precision),
            "test_recall": float(recall),
            "win_rate_before": float(win_rate_before),
            "win_rate_after": float(win_rate_after),
            "blocked_percentage": float(blocked_count / total_trades * 100 if total_trades > 0 else 0.0),
            "feature_importance": feature_importance_dict
        }

    def predict_loss_probability(self, features_dict: dict) -> float:
        """
        Dự đoán xác suất lệnh bị thua (chạm SL).
        Đầu vào: features_dict chứa các chỉ báo kỹ thuật thời gian thực.
        Trả về: float (từ 0.0 đến 1.0)
        """
        if self.model is None:
            # Nếu chưa huấn luyện mô hình, trả về xác suất mặc định (50/50)
            logger.warning("⚠️ Mô hình AI chưa được huấn luyện. Trả về xác suất mặc định 50%.")
            return 0.50

        try:
            # Chuẩn bị DataFrame cho 1 mẫu thử
            df_sample = pd.DataFrame([features_dict])
            df_sample = self.preprocess_data(df_sample)
            
            # Đảm bảo đầy đủ các cột đặc trưng
            for col in self.features:
                if col not in df_sample.columns:
                    df_sample[col] = 0.0
                    
            X_sample = df_sample[self.features]
            
            # Dự đoán xác suất cho lớp 1 (Thua)
            prob_loss = float(self.model.predict_proba(X_sample)[0, 1])
            return prob_loss
        except Exception as e:
            logger.error(f"❌ Lỗi khi chạy suy luận AI: {str(e)}")
            return 0.50

# Khởi tạo instance singleton
meta_labeler = MetaLabeler()
