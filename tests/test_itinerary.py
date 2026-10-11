import unittest
from datetime import date

from app.contracts import (
    Destination,
    ScoredDestination,
    TripRequest,
    WeatherDay,
)
from app.services import itinerary


class ItineraryServiceTests(unittest.TestCase):
    def test_haversine_known_coordinates(self):
        """haversine_km tính đúng khoảng cách cho cặp tọa độ đã biết (Hà Nội -> TP.HCM ~1,138 km, sai số < 1%)."""
        # Hà Nội: 21.0285, 105.8542
        # TP.HCM: 10.8231, 106.6297
        dist = itinerary.haversine_km(21.0285, 105.8542, 10.8231, 106.6297)
        self.assertAlmostEqual(dist, 1138.0, delta=12.0)  # sai số < 1%

    def test_is_open_rules(self):
        """Kiểm tra logic mở cửa theo Finding #21."""
        test_monday = date(2026, 10, 12)  # Thứ Hai (mon)
        test_tuesday = date(2026, 10, 13)  # Thứ Ba (tue)

        # 1. opening_hours is None -> luôn mở
        d_always_open = Destination(
            id=1, name="Công viên Mở", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.5,
            is_outdoor=True, opening_hours=None, tags=()
        )
        self.assertTrue(itinerary._is_open(d_always_open, test_monday, 480, 2.0))

        # 2. opening_hours rỗng {} -> lỗi dữ liệu -> False
        d_empty = Destination(
            id=2, name="Điểm Lỗi", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.5,
            is_outdoor=True, opening_hours={}, tags=()
        )
        self.assertFalse(itinerary._is_open(d_empty, test_monday, 480, 2.0))

        # 3. Đóng vào Thứ Hai, mở Thứ Ba: "08:00-17:00"
        d_closed_mon = Destination(
            id=3, name="Bảo tàng đóng thứ Hai", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=2.0,
            is_outdoor=False, opening_hours={"tue": "08:00-17:00"}, tags=()
        )
        self.assertFalse(itinerary._is_open(d_closed_mon, test_monday, 480, 2.0))
        self.assertTrue(itinerary._is_open(d_closed_mon, test_tuesday, 480, 2.0))

        # 4. Nhiều ca nghỉ trưa: "08:00-11:30, 13:30-17:00"
        d_split_shifts = Destination(
            id=4, name="Điểm nghỉ trưa", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=2.0,
            is_outdoor=False,
            opening_hours={"mon": "08:00-11:30, 13:30-17:00"}, tags=()
        )
        # Bắt đầu 08:30 kéo dài 2h (kết thúc 10:30 <= 11:30) -> True
        self.assertTrue(itinerary._is_open(d_split_shifts, test_monday, 510, 2.0))
        # Bắt đầu 11:00 kéo dài 2h (kết thúc 13:00 cắt ngang nghỉ trưa) -> False
        self.assertFalse(itinerary._is_open(d_split_shifts, test_monday, 660, 2.0))

        # 5. Mở qua nửa đêm: "18:00-02:00"
        d_night = Destination(
            id=5, name="Chợ Đêm", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=2.0,
            is_outdoor=True, opening_hours={"mon": "18:00-02:00"}, tags=()
        )
        # Bắt đầu 19:00 kéo dài 2h -> True
        self.assertTrue(itinerary._is_open(d_night, test_monday, 1140, 2.0))

    def test_no_duplicate_destinations_across_trip(self):
        """Mọi địa điểm trong chuyến đi không bị trùng lặp."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=5000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="thoai_mai",
        )
        dests = [
            Destination(
                id=i, name=f"Điểm {i}", province="Đà Lạt",
                latitude=11.9 + i * 0.01, longitude=108.4 + i * 0.01,
                category_id=1, price_range=1, noise_level=2,
                duration_hours=1.5, is_outdoor=True, opening_hours=None, tags=()
            )
            for i in range(1, 15)
        ]
        ranked = [ScoredDestination(destination=d, score=1.0 - i * 0.05, cb_score=1.0 - i * 0.05) for i, d in enumerate(dests)]

        day_plans, warnings = itinerary.build_itinerary(ranked, req, [])
        all_ids = [item.destination.id for dp in day_plans for item in dp.items]
        self.assertEqual(len(all_ids), len(set(all_ids)), "Không được có địa điểm trùng lặp trong cả chuyến đi")

    def test_rainy_day_prioritizes_indoor_and_warns_if_exhausted(self):
        """Ngày mưa ưu tiên điểm trong nhà; nếu hết trong nhà phải xếp ngoài trời thì có cảnh báo."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=2000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        # Chỉ có 1 điểm indoor và nhiều điểm outdoor
        d_indoor = Destination(
            id=10, name="Bảo tàng trong nhà", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.5,
            is_outdoor=False, opening_hours=None, tags=()
        )
        d_outdoor = Destination(
            id=20, name="Thung lũng ngoài trời", province="Đà Lạt",
            latitude=11.91, longitude=108.41, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.5,
            is_outdoor=True, opening_hours=None, tags=()
        )
        ranked = [
            ScoredDestination(destination=d_outdoor, score=0.9, cb_score=0.9),
            ScoredDestination(destination=d_indoor, score=0.8, cb_score=0.8),
        ]
        # Thời tiết mưa cả ngày
        rainy_weather = [
            WeatherDay(
                date=date(2026, 11, 1),
                temp_min=18.0, temp_max=22.0, humidity=85,
                rain_prob={"morning": 0.8, "afternoon": 0.8, "evening": 0.8},
                condition="Mưa to", is_severe=False
            )
        ]

        day_plans, warnings = itinerary.build_itinerary(ranked, req, rainy_weather)
        items = day_plans[0].items
        # Buổi sáng phải ưu tiên điểm indoor d_indoor dù d_outdoor có điểm cao hơn
        self.assertTrue(len(items) >= 1)
        self.assertEqual(items[0].destination.id, 10)
        # Vì chỉ có 1 indoor, điểm tiếp theo hoặc slot sau phải fallback outdoor và sinh warning
        if any(it.destination.is_outdoor for it in items):
            self.assertTrue(any("mưa" in w.lower() for w in warnings))

    def test_empty_slot_generates_warning_when_out_of_destinations(self):
        """Hết địa điểm hợp lệ thì slot trống và sinh cảnh báo."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=2000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        # Chỉ có đúng 1 điểm đến cho cả ngày 3 slot
        d1 = Destination(
            id=1, name="Điểm duy nhất", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.5,
            is_outdoor=True, opening_hours=None, tags=()
        )
        ranked = [ScoredDestination(destination=d1, score=0.9, cb_score=0.9)]
        day_plans, warnings = itinerary.build_itinerary(ranked, req, [])

        total_items = sum(len(dp.items) for dp in day_plans)
        self.assertEqual(total_items, 1)
        # Phải có cảnh báo không đủ địa điểm
        self.assertTrue(any("không đủ địa điểm" in w.lower() for w in warnings))


if __name__ == "__main__":
    unittest.main()
