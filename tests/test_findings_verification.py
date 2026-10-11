import unittest
from datetime import date, datetime, timedelta, timezone
from app.contracts import (
    Destination,
    TripRequest,
    WeatherDay,
    CF_MIN_TOTAL_RATINGS,
    CF_MIN_USER_RATINGS,
)
from app.services import collaborative, content_based, weather, itinerary, budget
from app import create_app
from tests.fakes import FakeRepo


class FindingsVerificationTests(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo([])
        self.app = create_app(repo=self.repo)
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-secret-key"
        self.client = self.app.test_client()

    def test_collaborative_mean_centering_and_duplicates(self):
        # Finding #13 & #14: Gộp duplicate ratings và trừ mean
        ratings = []
        for u in range(1, 15):
            for d in range(1, 6):
                if u == 1 and d == 1:
                    ratings.append((1, 1, 5))
                    ratings.append((1, 1, 3))
                else:
                    score = 5 if u % 2 == 0 else 3
                    ratings.append((u, d, score))

        ratings.append((2, 10, 5))
        ratings.append((3, 10, 4))

        candidates = [10, 999]
        scores = collaborative.score(1, ratings, candidates)
        self.assertIn(10, scores)
        self.assertNotIn(999, scores)
        self.assertGreaterEqual(scores[10], 0.0)
        self.assertLessEqual(scores[10], 1.0)

    def test_content_based_price_fit_monotone(self):
        # Finding #12: Khách tiết kiệm (tiet_kiem) thì giá rẻ phải điểm cao hơn giá đắt
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        dest_cheap = Destination(
            id=1,
            name="Điểm rẻ",
            province="Đà Lạt",
            latitude=11.9,
            longitude=108.4,
            category_id=1,
            price_range=1,
            noise_level=3,
            duration_hours=1.5,
            is_outdoor=True,
            tags=("thien_nhien",),
        )
        dest_expensive = Destination(
            id=2,
            name="Điểm đắt",
            province="Đà Lạt",
            latitude=11.9,
            longitude=108.4,
            category_id=1,
            price_range=4,
            noise_level=3,
            duration_hours=1.5,
            is_outdoor=True,
            tags=("thien_nhien",),
        )

        scores = content_based.score(req, [dest_cheap, dest_expensive])
        self.assertGreater(scores[1], scores[2])

    def test_weather_severe_and_missing_slots(self):
        # Finding #15: slot thiếu mốc gán None, is_severe gán rain_prob = 1.0
        sample_raw = {
            "list": [
                {
                    "dt": int(datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc).timestamp()),
                    "main": {"temp": 22.0, "temp_min": 20.0, "temp_max": 24.0, "humidity": 80},
                    "weather": [{"id": 503, "description": "mưa rất to"}],
                    "wind": {"speed": 5.0},
                    "pop": 0.9,
                }
            ]
        }
        parsed = weather.parse_forecast(sample_raw, date(2026, 11, 1), 1)
        self.assertEqual(len(parsed), 1)
        w_day = parsed[0]
        self.assertTrue(w_day.is_severe)
        self.assertEqual(w_day.rain_prob["morning"], 1.0)
        self.assertEqual(w_day.rain_prob["afternoon"], 1.0)
        self.assertEqual(w_day.rain_prob["evening"], 1.0)

    def test_weather_cache_fallback(self):
        # Finding #16: fetch lỗi fallback cache cũ
        old_time = datetime.now(timezone.utc) - timedelta(hours=10)
        cache_store = {"Đà Lạt": ({"list": []}, old_time)}

        def mock_fetch(province):
            raise ConnectionError("API OpenWeather down")

        def mock_get(prov):
            return cache_store.get(prov)

        res = weather.get_forecast("Đà Lạt", date(2026, 11, 1), 1, fetch=mock_fetch, cache_get=mock_get)
        self.assertEqual(res, [])

    def test_itinerary_multi_shift_opening_hours(self):
        # Finding #21: Nhiều ca mở cửa
        d = Destination(
            id=1,
            name="Điểm chia ca",
            province="Đà Lạt",
            latitude=11.9,
            longitude=108.4,
            category_id=1,
            price_range=2,
            noise_level=2,
            duration_hours=1.5,
            is_outdoor=False,
            tags=("van_hoa",),
            opening_hours={"mon": "08:00-11:30,13:30-17:00"},
        )
        mon = date(2026, 10, 12)
        self.assertTrue(itinerary._is_open(d, mon, 8 * 60 + 30, 1.5))
        self.assertFalse(itinerary._is_open(d, mon, 11 * 60, 1.5))
        self.assertTrue(itinerary._is_open(d, mon, 14 * 60, 1.5))

    def test_budget_per_day_allocation(self):
        # Finding #18: per_day_allocation
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=3,
            budget=3000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="thoai_mai",
        )
        cb = budget.allocate(req, ())
        self.assertEqual(cb.per_day, 1000000)
        self.assertIn("ve_vao_cua", cb.per_day_allocation)
        self.assertEqual(cb.per_day_allocation["ve_vao_cua"], cb.allocation["ve_vao_cua"] // 3)

    def test_csrf_protection(self):
        # Finding #2: POST không token bị chặn 403 Forbidden
        res = self.client.post("/login", data={"email": "a@b.com", "password": "123"})
        self.assertEqual(res.status_code, 403)

        with self.client.session_transaction() as sess:
            sess["csrf_token"] = "valid-token-123"

        res_ok = self.client.post(
            "/login",
            data={"csrf_token": "valid-token-123", "email": "nonexistent@b.com", "password": "wrongpassword123"},
        )
        self.assertNotEqual(res_ok.status_code, 403)

    def test_health_check_endpoint(self):
        # Finding #10: /health endpoint
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("status"), "ok")

    def test_soft_delete_destination(self):
        # Finding #23: Xóa mềm is_active=False
        dest_id = self.repo.save_destination({
            "name": "Điểm thử xóa",
            "province": "Đà Lạt",
            "latitude": 11.9,
            "longitude": 108.4,
            "category_id": 1,
            "price_range": 2,
            "noise_level": 2,
            "duration_hours": 1.5,
            "is_outdoor": True,
            "tags": ("thien_nhien",),
        })
        self.repo.delete_destination(dest_id)
        d_after = self.repo.get_destination(dest_id)
        self.assertFalse(d_after.is_active)

    def test_non_owner_access_returns_404(self):
        # Finding #9: Người không phải chủ luôn nhận 404
        # Tạo user 1 và user 2
        u1_id = self.repo.create_user("u1@example.com", "hash", "User 1")
        u2_id = self.repo.create_user("u2@example.com", "hash", "User 2")

        # Đăng nhập với u1
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": u1_id, "email": "u1@example.com", "full_name": "User 1", "is_admin": False}
            sess["csrf_token"] = "tok"

        # User 1 truy cập trip ID 9999 không tồn tại -> 404
        res = self.client.get("/trips/9999")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
