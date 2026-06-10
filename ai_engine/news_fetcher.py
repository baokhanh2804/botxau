import os
import json
import logging
import httpx
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("botxau.news")

# Thư mục chứa dữ liệu cache
CACHE_DIR = Path(__file__).resolve().parent
CALENDAR_FILE = CACHE_DIR / "economic_calendar.json"

class NewsFetcher:
    """Bộ thu thập và phân tích khoảng cách tin tức kinh tế phục vụ AI Filter"""
    
    def __init__(self):
        self.news_events = []
        self.load_cache()
        if not self.news_events:
            self.generate_mock_historical_news()

    def load_cache(self):
        """Tải lịch tin tức từ file JSON lưu trữ cục bộ"""
        if CALENDAR_FILE.exists():
            try:
                with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Chuyển đổi timestamp dạng chuỗi sang float
                    self.news_events = []
                    for item in data:
                        self.news_events.append({
                            "time": float(item["time"]),
                            "event": item["event"],
                            "country": item["country"],
                            "impact": item["impact"]
                        })
                logger.info(f"📁 Đã tải {len(self.news_events)} tin tức kinh tế từ cache.")
            except Exception as e:
                logger.error(f"❌ Không tải được file cache tin tức: {str(e)}")

    def save_cache(self):
        """Lưu trữ danh sách tin tức xuống file JSON cục bộ"""
        try:
            with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
                json.dump(self.news_events, f, indent=4, ensure_ascii=False)
            logger.info("💾 Đã lưu cache tin tức kinh tế.")
        except Exception as e:
            logger.error(f"❌ Lỗi khi lưu cache tin tức: {str(e)}")

    def fetch_live_news(self) -> bool:
        """
        [Nâng cấp Production] Lấy lịch tin từ các API miễn phí hoặc RSS feeds
        Ở bản Beta này, chúng ta sẽ mô phỏng kết nối và fallback về dữ liệu giả lập chất lượng cao.
        """
        try:
            # Ví dụ tích hợp API giả định hoặc RSS ForexFactory
            # URL: https://nfs.forexfactory1.com/public.php (Ví dụ)
            # Ở đây ta sẽ giả định gọi API thành công hoặc nạp dữ liệu lịch thực tế.
            logger.info("📡 Đang cố gắng cập nhật lịch tin tức trực tuyến...")
            # Nếu chạy thật, ta sẽ parse RSS hoặc gọi API và thêm vào self.news_events
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối API lịch tin: {str(e)}")
            return False

    def generate_mock_historical_news(self):
        """
        Tự động tạo lịch tin tức giả lập chất lượng cao (USD CPI, NFP, FOMC)
        từ năm 2024 đến hết 2026. Điều này rất quan trọng để chạy Backtest ngoại tuyến
        mà không cần Internet.
        """
        logger.info("⚙️ Đang tạo dữ liệu tin tức giả lập chất lượng cao cho XAU/USD...")
        events = []
        
        # Thiết lập khoảng thời gian: Từ 01/01/2024 đến 31/12/2026
        start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2026, 12, 31, tzinfo=timezone.utc)
        
        curr_date = start_date
        while curr_date <= end_date:
            # 1. Non-Farm Payrolls (NFP) - Thứ Sáu đầu tiên của tháng lúc 13:30 UTC (hoặc 12:30 tùy DST, ta mặc định 13:30)
            if curr_date.weekday() == 4: # Thứ 6
                # Kiểm tra xem có phải Thứ 6 đầu tiên không (ngày từ 1 đến 7)
                if 1 <= curr_date.day <= 7:
                    nfp_time = curr_date.replace(hour=13, minute=30, second=0, microsecond=0)
                    events.append({
                        "time": nfp_time.timestamp(),
                        "event": "USD Non-Farm Payrolls & Unemployment Rate",
                        "country": "USD",
                        "impact": "HIGH"
                    })
            
            # 2. US CPI (Chỉ số lạm phát) - Thường rơi vào giữa tháng (từ ngày 10 đến ngày 15), Thứ Ba hoặc Thứ Tư lúc 13:30 UTC
            if curr_date.day in [11, 12, 13, 14] and curr_date.weekday() in [1, 2]: # Thứ 3 hoặc Thứ 4
                cpi_time = curr_date.replace(hour=13, minute=30, second=0, microsecond=0)
                events.append({
                    "time": cpi_time.timestamp(),
                    "event": "USD Consumer Price Index (CPI) MoM/YoY",
                    "country": "USD",
                    "impact": "HIGH"
                })

            # 3. FOMC Interest Rate Decision (Quyết định lãi suất Fed) - Thường vào Thứ Tư lúc 19:00 UTC, khoảng 6 tuần một lần.
            # Ta giả lập bằng cách tạo lịch định kỳ mỗi 6 tuần vào ngày Thứ Tư
            if curr_date.weekday() == 2: # Thứ Tư
                # Lấy số tuần trong năm, nếu chia hết cho 6
                week_num = curr_date.isocalendar()[1]
                if week_num % 6 == 0:
                    fomc_time = curr_date.replace(hour=19, minute=0, second=0, microsecond=0)
                    events.append({
                        "time": fomc_time.timestamp(),
                        "event": "USD FOMC Interest Rate Decision & Press Conference",
                        "country": "USD",
                        "impact": "HIGH"
                    })

            curr_date += timedelta(days=1)
            
        self.news_events = events
        # Sắp xếp tin tức theo thời gian tăng dần
        self.news_events.sort(key=lambda x: x["time"])
        self.save_cache()

    def get_minutes_to_next_major_news(self, current_timestamp: float) -> float:
        """
        Tính khoảng cách thời gian (bằng phút) từ mốc thời gian hiện tại
        đến tin tức mạnh (HIGH impact) gần nhất (bao gồm cả tin sắp tới và tin vừa xảy ra).
        Nếu tin vừa xảy ra 10 phút trước -> trả về 10.
        Nếu tin sắp xảy ra sau 20 phút -> trả về 20.
        """
        if not self.news_events:
            return 999999.0 # Không có tin tức nào

        min_diff = 999999.0
        for event in self.news_events:
            if event["impact"] != "HIGH":
                continue
            
            diff_minutes = abs(event["time"] - current_timestamp) / 60.0
            if diff_minutes < min_diff:
                min_diff = diff_minutes
                
        return min_diff

    def is_major_news_near(self, current_timestamp: float, threshold_minutes: float = 60.0) -> bool:
        """Kiểm tra xem có tin tức đỏ nào trong vòng X phút hay không (trước hoặc sau)"""
        return self.get_minutes_to_next_major_news(current_timestamp) <= threshold_minutes

# Khởi tạo instance singleton
news_fetcher = NewsFetcher()
if __name__ == "__main__":
    # Test chạy trực tiếp
    import time
    now = time.time()
    minutes = news_fetcher.get_minutes_to_next_major_news(now)
    print(f"Khoảng cách đến tin tức USD quan trọng gần nhất: {minutes:.2f} phút.")
