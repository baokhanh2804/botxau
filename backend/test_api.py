import sys
import json
import logging
from pathlib import Path

# Them thu muc goc vao PYTHONPATH de co the import backend
sys.path.append(str(Path(__file__).resolve().parent.parent))

try:
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.config import settings
    from backend.database import engine, Base
except ImportError as e:
    print(f"[FAIL] Loi: Khong import duoc cac mo-dun backend. Chi tiet: {str(e)}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("botxau.test")

# Dong bo database truoc khi test
print("[TEST] Dang xoa va dong bo lai database de test sach...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("[TEST] Khoi tao database completed.")

def run_tests():
    print("==================================================")
    print("[TEST] BAT DAU CHAY THU NGHIEM TICH HOP BOTXAU")
    print("==================================================")

    # Su dung Context Manager de kich hoat event startup cua FastAPI (gồm cả tự động train AI)
    with TestClient(app) as client:
        # 1. Test GET /api/dashboard
        print("\n--- Test 1: Truy cap API Dashboard ---")
        response = client.get("/api/dashboard")
        if response.status_code == 200:
            data = response.json()
            print("[PASS] Thanh cong! Phan hoi tu Dashboard:")
            print(f"   - Ten tai khoan: {data['account'].get('name')}")
            print(f"   - So du (Balance): {data['account'].get('balance')}$")
            print(f"   - Tai san (Equity): {data['account'].get('equity')}$")
            print(f"   - So vi the dang mo: {len(data['open_positions'])}")
            print(f"   - Trang thai AI Filter: {data['ai_settings']['status']}")
        else:
            print(f"[FAIL] That bai! Status code: {response.status_code}")
            return

        # 2. Test Webhook: Lenh BUY hop le (Thoa man Quan ly von)
        print("\n--- Test 2: Gui Webhook lenh BUY hop le ---")
        payload = {
            "strategy_name": "RSI_EMA_Cross",
            "symbol": "XAUUSD",
            "action": "BUY",
            "price": 2350.50,
            "stop_loss": 2340.00,  # SL cach 10$ -> Rui ro gioi han
            "take_profit": 2365.00,
            "token": settings.SECRET_WEBHOOK_TOKEN
        }
        response = client.post("/api/webhook", json=payload)
        print(f"Status code: {response.status_code}")
        res_data = response.json()
        print("Phan hoi:", json.dumps(res_data, indent=2))
        if response.status_code == 201 and res_data.get("status") in ["SUCCESS", "BLOCKED_BY_AI", "HALF_SIZE"]:
            print("[PASS] Thanh cong! Lenh da duoc xu ly qua Risk + AI Filter.")
        else:
            print("[FAIL] That bai!")

        # 3. Test Webhook: Lenh BUY KHONG co Stop Loss (Vi pham luat Risk Manager)
        print("\n--- Test 3: Gui Webhook lenh BUY khong co Stop Loss ---")
        payload_no_sl = {
            "strategy_name": "RSI_EMA_Cross",
            "symbol": "XAUUSD",
            "action": "BUY",
            "price": 2350.50,
            "token": settings.SECRET_WEBHOOK_TOKEN
        }
        response = client.post("/api/webhook", json=payload_no_sl)
        print(f"Status code: {response.status_code}")
        res_data = response.json()
        print("Phan hoi:", json.dumps(res_data, indent=2))
        if response.status_code == 201 and res_data.get("status") == "REJECTED_BY_RISK":
            print("[PASS] Thanh cong! Risk Manager da chan lenh khong co SL.")
        else:
            print("[FAIL] That bai!")

        # 4. Test Webhook: Sai Webhook Token
        print("\n--- Test 4: Gui Webhook voi Token sai ---")
        payload_wrong_token = {
            "strategy_name": "RSI_EMA_Cross",
            "symbol": "XAUUSD",
            "action": "BUY",
            "price": 2350.50,
            "stop_loss": 2340.00,
            "token": "wrong_token_123"
        }
        response = client.post("/api/webhook", json=payload_wrong_token)
        print(f"Status code: {response.status_code} (Mong doi: 401)")
        if response.status_code == 401:
            print("[PASS] Thanh cong! He thong tu choi truy cap khong hop le.")
        else:
            print("[FAIL] That bai!")

        # 5. Test Webhook: Lenh dong tat ca (CLOSE_ALL)
        print("\n--- Test 5: Gui Webhook CLOSE_ALL (Panic) ---")
        payload_close = {
            "strategy_name": "RSI_EMA_Cross",
            "symbol": "XAUUSD",
            "action": "CLOSE_ALL",
            "price": 2348.00,
            "token": settings.SECRET_WEBHOOK_TOKEN
        }
        response = client.post("/api/webhook", json=payload_close)
        print(f"Status code: {response.status_code}")
        res_data = response.json()
        print("Phan hoi:", json.dumps(res_data, indent=2))
        if response.status_code == 201 and res_data.get("status") == "CLOSED_SUCCESS":
            print("[PASS] Thanh cong! Da chot toan bo cac vi the.")
        else:
            print("[FAIL] That bai!")

    print("\n==================================================")
    print("[SUCCESS] TAT CA CAC BAI THU NGHIEM DA HOAN THANH!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
