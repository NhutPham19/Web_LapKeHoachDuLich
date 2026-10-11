import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from app.contracts import WeatherDay
from app.services import weather

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "owm_forecast.json"


class WeatherServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
            cls.raw_fixture = json.load(f)

    def test_parse_forecast_vn_timezone_and_slots(self):
        """parse_forecast chuyển đổi đúng giờ VN (+7) và nhóm vào các slot (morning, afternoon, evening)."""
        # Ngày 2026-10-12 có trong fixture
        start = date(2026, 10, 12)
        days = 1
        forecast = weather.parse_forecast(self.raw_fixture, start, days)
        self.assertEqual(len(forecast), 1)
        w_day = forecast[0]
        self.assertEqual(w_day.date, start)
        self.assertIn("morning", w_day.rain_prob)
        self.assertIn("afternoon", w_day.rain_prob)
        self.assertIn("evening", w_day.rain_prob)
        # Các giá trị pop phải nằm trong [0.0, 1.0] hoặc None
        for slot in ("morning", "afternoon", "evening"):
            val = w_day.rain_prob[slot]
            if val is not None:
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 1.0)

    def test_parse_forecast_severe_weather_handling(self):
        """Ngày 2026-10-14 có giông bão (id 202) -> is_severe=True và mọi slot rain_prob=1.0 (Finding #15)."""
        start = date(2026, 10, 14)
        forecast = weather.parse_forecast(self.raw_fixture, start, 1)
        self.assertEqual(len(forecast), 1)
        w_day = forecast[0]
        self.assertTrue(w_day.is_severe)
        self.assertEqual(w_day.rain_prob["morning"], 1.0)
        self.assertEqual(w_day.rain_prob["afternoon"], 1.0)
        self.assertEqual(w_day.rain_prob["evening"], 1.0)

    def test_date_out_of_range_returns_no_weather_day(self):
        """Ngày ngoài tầm 5 ngày (vd 2026-10-25) không có trong kết quả trả về."""
        start = date(2026, 10, 25)
        forecast = weather.parse_forecast(self.raw_fixture, start, 2)
        self.assertEqual(len(forecast), 0)

    def test_get_forecast_uses_valid_cache_without_fetch(self):
        """Khi cache còn hạn (< 3h), get_forecast dùng dữ liệu cache và không gọi hàm fetch."""
        mock_fetch = MagicMock(return_value={"list": []})
        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        cached_at = now - timedelta(hours=1)  # cache 1 giờ trước (< 3h)

        def mock_cache_get(prov: str):
            return (self.raw_fixture, cached_at)

        mock_cache_put = MagicMock()

        res = weather.get_forecast(
            "Đà Lạt",
            date(2026, 10, 12),
            1,
            fetch=mock_fetch,
            cache_get=mock_cache_get,
            cache_put=mock_cache_put,
            now=now,
        )
        mock_fetch.assert_not_called()
        mock_cache_put.assert_not_called()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].date, date(2026, 10, 12))

    def test_get_forecast_calls_fetch_when_cache_expired(self):
        """Khi cache đã hết hạn (> 3h), get_forecast gọi fetch và ghi lại vào cache."""
        mock_fetch = MagicMock(return_value=self.raw_fixture)
        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        cached_at = now - timedelta(hours=4)  # cache 4 giờ trước (> 3h)

        def mock_cache_get(prov: str):
            return (self.raw_fixture, cached_at)

        mock_cache_put = MagicMock()

        res = weather.get_forecast(
            "Đà Lạt",
            date(2026, 10, 12),
            1,
            fetch=mock_fetch,
            cache_get=mock_cache_get,
            cache_put=mock_cache_put,
            now=now,
        )
        mock_fetch.assert_called_once_with("Đà Lạt")
        mock_cache_put.assert_called_once_with("Đà Lạt", self.raw_fixture)
        self.assertEqual(len(res), 1)

    def test_get_forecast_fallback_to_stale_cache_on_fetch_error(self):
        """Finding #16: Khi fetch bị lỗi mạng nhưng có cache cũ (kể cả hết hạn), fallback dùng cache cũ."""
        def mock_failing_fetch(prov: str):
            raise ConnectionError("Mạng chập chờn")

        now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
        cached_at = now - timedelta(hours=10)  # cache cũ 10 giờ trước

        def mock_cache_get(prov: str):
            return (self.raw_fixture, cached_at)

        res = weather.get_forecast(
            "Đà Lạt",
            date(2026, 10, 12),
            1,
            fetch=mock_failing_fetch,
            cache_get=mock_cache_get,
            now=now,
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].date, date(2026, 10, 12))


if __name__ == "__main__":
    unittest.main()
