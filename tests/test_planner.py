import json
import unittest
from datetime import date
from pathlib import Path

from app.contracts import Destination, TripPlan, TripRequest
from app.services import planner, weather
from tests.fixtures.ratings import NATURE_USERS, SYNTHETIC_RATINGS

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture_destinations() -> list[Destination]:
    with open(FIXTURES_DIR / "destinations.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    dests = []
    for item in data["destinations"]:
        val = dict(item)
        val["tags"] = tuple(val["tags"])
        dests.append(Destination(**val))
    return dests


def load_fixture_weather(start_date: date, days: int):
    with open(FIXTURES_DIR / "owm_forecast.json", "r", encoding="utf-8") as f:
        raw = json.load(f)
    return weather.parse_forecast(raw, start_date, days)


class PlannerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destinations = load_fixture_destinations()

    def test_generate_plan_end_to_end(self):
        """generate_plan end-to-end trên fixture dữ liệu mẫu trả về TripPlan hợp lệ."""
        start_date = date(2026, 10, 12)
        req = TripRequest(
            province="Đà Lạt",
            start_date=start_date,
            days=2,
            budget=3000000,
            num_people=2,
            interests=("thien_nhien", "yen_tinh"),
            travel_style="thoai_mai",
            user_id=NATURE_USERS[0],
        )
        weather_list = load_fixture_weather(start_date, 2)
        plan = planner.generate_plan(req, self.destinations, SYNTHETIC_RATINGS, weather_list)

        self.assertIsInstance(plan, TripPlan)
        self.assertEqual(plan.request, req)
        self.assertEqual(len(plan.days), 2)
        self.assertEqual(plan.cost.budget, req.budget)
        self.assertEqual(sum(plan.cost.allocation.values()), req.budget)

        # Kiểm tra không có địa điểm trùng lặp
        all_dests = [it.destination.id for d in plan.days for it in d.items]
        self.assertEqual(len(all_dests), len(set(all_dests)))

    def test_different_interests_produce_different_plans(self):
        """Tiêu chí nghiệm thu (DoD B / Yêu cầu giảng viên): Hai user khác sở thích phải nhận kế hoạch khác nhau."""
        start_date = date(2026, 10, 12)
        weather_list = load_fixture_weather(start_date, 1)

        # User 1: Thích thiên nhiên, yên tĩnh
        req_nature = TripRequest(
            province="Đà Lạt",
            start_date=start_date,
            days=1,
            budget=2000000,
            num_people=1,
            interests=("thien_nhien", "yen_tinh"),
            travel_style="tiet_kiem",
        )
        plan_nature = planner.generate_plan(req_nature, self.destinations, SYNTHETIC_RATINGS, weather_list)
        dest_ids_nature = [it.destination.id for d in plan_nature.days for it in d.items]

        # User 2: Thích ẩm thực, mua sắm, vui chơi
        req_food = TripRequest(
            province="Đà Lạt",
            start_date=start_date,
            days=1,
            budget=2000000,
            num_people=1,
            interests=("am_thuc", "mua_sam", "vui_choi"),
            travel_style="thoai_mai",
        )
        plan_food = planner.generate_plan(req_food, self.destinations, SYNTHETIC_RATINGS, weather_list)
        dest_ids_food = [it.destination.id for d in plan_food.days for it in d.items]

        # Hai danh sách địa điểm phải khác nhau ít nhất ở điểm đầu tiên hoặc tổng thể
        self.assertNotEqual(
            dest_ids_nature,
            dest_ids_food,
            "Hai người dùng có sở thích trái ngược nhau phải nhận danh sách gợi ý khác nhau",
        )
        # Cụ thể: User thiên nhiên phải có Đồi Thông (id 1) ở vị trí đầu tiên
        self.assertEqual(dest_ids_nature[0], 1)
        # User ẩm thực/vui chơi phải chọn Chợ Ẩm thực (id 3)
        self.assertIn(3, dest_ids_food)


if __name__ == "__main__":
    unittest.main()
