import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.contracts import (BUDGET_SPLIT, INTERESTS, PROVINCES, PROVINCE_COORDS, TEST_PROVINCES, TIME_SLOTS, CostBreakdown,
                           DayPlan, Destination, ItineraryItem, TripPlan, TripRequest, WeatherDay)
from tests.fakes import FakeRepo
from tests.fixtures.ratings import CULTURE_USERS, NATURE_USERS, SYNTHETIC_RATINGS


FIXTURES = Path(__file__).parent / "fixtures"
REPOSITORY_METHODS = {
    "create_user", "get_user_by_email", "get_user", "save_preferences", "get_preferences",
    "list_destinations", "get_destination", "save_destination", "delete_destination",
    "list_categories", "save_category", "delete_category", "save_trip", "get_trip",
    "get_trip_by_token", "list_trips", "delete_trip", "add_item", "update_item", "delete_item",
    "set_sharing", "set_status", "save_rating", "list_approved_ratings", "list_pending_ratings",
    "set_rating_approved", "get_weather_cache", "put_weather_cache", "admin_stats",
}


def load_json(name):
    with (FIXTURES / name).open(encoding="utf-8") as fixture:
        return json.load(fixture)


def destination_from_json(data):
    values = dict(data)
    values["tags"] = tuple(values["tags"])
    return Destination(**values)


def weather_from_json(data):
    return WeatherDay(date.fromisoformat(data["date"]), data["temp_min"], data["temp_max"],
                      data["humidity"], data["rain_prob"], data["condition"], data["is_severe"])


def plan_from_json(data):
    request_data = data["request"]
    request = TripRequest(request_data["province"], date.fromisoformat(request_data["start_date"]),
                          request_data["days"], request_data["budget"], request_data["num_people"],
                          tuple(request_data["interests"]), request_data["travel_style"],
                          request_data["user_id"])
    days = []
    for day in data["days"]:
        items = tuple(ItineraryItem(destination_from_json(item["destination"]), item["day_number"],
                                    item["time_slot"], item["order_in_slot"], item["estimated_cost"],
                                    item["notes"], item["id"]) for item in day["items"])
        weather = weather_from_json(day["weather"]) if day["weather"] else None
        days.append(DayPlan(day["day_number"], date.fromisoformat(day["date"]), items, weather))
    cost_data = data["cost"]
    cost = CostBreakdown(cost_data["budget"], cost_data["per_day"], cost_data["allocation"],
                         cost_data["tickets_estimated"], cost_data["within_budget"])
    return TripPlan(request, tuple(days), cost, tuple(data["warnings"]))


class FixtureSanityTests(unittest.TestCase):
    def test_destinations_match_destination_contract(self):
        data = load_json("destinations.json")
        self.assertIn("GIẢ LẬP", data["fixture_notice"])
        self.assertGreaterEqual(len(data["destinations"]), 12)
        destinations = [destination_from_json(item) for item in data["destinations"]]
        self.assertEqual(len({destination.id for destination in destinations}), len(destinations))
        self.assertEqual({destination.province for destination in destinations}, set(TEST_PROVINCES))
        self.assertEqual({destination.price_range for destination in destinations}, {1, 2, 3, 4})
        self.assertEqual({destination.noise_level for destination in destinations}, {1, 2, 3, 4, 5})
        self.assertEqual({destination.is_outdoor for destination in destinations}, {False, True})
        for destination in destinations:
            self.assertIsInstance(destination.tags, tuple)
            self.assertTrue(set(destination.tags).issubset(INTERESTS))
            self.assertGreater(destination.duration_hours, 0)
            self.assertIn("giả lập", destination.description.lower())

    def test_provinces_derived_from_province_coords(self):
        """Kiểm tra bất biến: PROVINCES được derive 100% từ PROVINCE_COORDS (Single Source of Truth)."""
        self.assertEqual(set(PROVINCES), set(PROVINCE_COORDS.keys()))
        self.assertTrue(set(TEST_PROVINCES).issubset(set(PROVINCES)))

    def test_ratings_are_structured_opposing_synthetic_groups(self):
        self.assertGreaterEqual(len(SYNTHETIC_RATINGS), 60)
        self.assertTrue(all(isinstance(rating, tuple) and len(rating) == 3 for rating in SYNTHETIC_RATINGS))
        self.assertTrue(all(1 <= score <= 5 for _, _, score in SYNTHETIC_RATINGS))
        nature_high = [score for user, _, score in SYNTHETIC_RATINGS if user in NATURE_USERS and score == 5]
        culture_high = [score for user, _, score in SYNTHETIC_RATINGS if user in CULTURE_USERS and score == 5]
        self.assertEqual(len(nature_high), len(culture_high))
        self.assertTrue(set(NATURE_USERS).isdisjoint(CULTURE_USERS))

    def test_owm_fixture_has_five_days_rainy_morning_and_severe_weather(self):
        forecast = load_json("owm_forecast.json")
        self.assertEqual(forecast["cod"], "200")
        self.assertEqual(forecast["cnt"], 40)
        self.assertEqual(len(forecast["list"]), 40)
        local_entries = [(entry, datetime.fromtimestamp(entry["dt"], timezone.utc) + timedelta(hours=7))
                         for entry in forecast["list"]]
        self.assertEqual(len({entry["dt_txt"][:10] for entry in forecast["list"]}), 5)
        self.assertTrue(any(6 <= local.hour <= 11 and entry["pop"] >= 0.5
                            for entry, local in local_entries))
        self.assertTrue(any(200 <= entry["weather"][0]["id"] <= 299 or entry["wind"]["speed"] >= 17
                            for entry in forecast["list"]))
        for entry in forecast["list"]:
            self.assertTrue({"dt", "main", "weather", "clouds", "wind", "visibility", "pop", "sys", "dt_txt"}
                            .issubset(entry))

    def test_sample_trip_plan_reconstructs_contract_types(self):
        data = load_json("sample_trip_plan.json")
        self.assertIn("GIẢ LẬP", data["fixture_notice"])
        plan = plan_from_json(data)
        self.assertIsInstance(plan, TripPlan)
        self.assertIsInstance(plan.request, TripRequest)
        self.assertEqual(plan.request.days, len(plan.days))
        self.assertEqual(plan.cost.per_day, plan.cost.budget // plan.request.days)
        self.assertEqual(set(plan.cost.allocation), set(BUDGET_SPLIT))
        self.assertEqual(sum(plan.cost.allocation.values()), plan.cost.budget)
        self.assertTrue(all(item.time_slot in TIME_SLOTS for day in plan.days for item in day.items))
        self.assertIsInstance(plan.days[0].weather, WeatherDay)
        self.assertIsNone(plan.days[1].weather)

    def test_fake_repo_implements_protocol_and_core_memory_behavior(self):
        self.assertTrue(all(callable(getattr(FakeRepo, method, None)) for method in REPOSITORY_METHODS))
        destinations = [destination_from_json(item) for item in load_json("destinations.json")["destinations"]]
        destination = destinations[0]
        repo = FakeRepo(destinations)
        user_id = repo.create_user("fake@example.com", "hash", "Người dùng giả")
        repo.save_preferences(user_id, ("thien_nhien",), "tiet_kiem")
        self.assertEqual(repo.get_preferences(user_id)["interests"], ["thien_nhien"])
        plan = plan_from_json(load_json("sample_trip_plan.json"))
        trip_id = repo.save_trip(user_id, "Kế hoạch giả", plan)
        item_id = repo.add_item(trip_id, destination.id, 2, "morning", 1, 0)
        self.assertGreater(item_id, 3)
        token = repo.set_sharing(trip_id, True)
        self.assertEqual(repo.get_trip_by_token(token).id, trip_id)
        rating_id = repo.save_rating(user_id, destination.id, trip_id, 5, "Tốt")
        repo.set_rating_approved(rating_id, True)
        self.assertEqual(repo.list_approved_ratings(), [(user_id, destination.id, 5)])
        self.assertEqual(repo.get_destination(destination.id).avg_rating, 5.0)
        repo.put_weather_cache("Đà Lạt", {"source": "fake"})
        self.assertEqual(repo.get_weather_cache("Đà Lạt")[0]["source"], "fake")


if __name__ == "__main__":
    unittest.main()
