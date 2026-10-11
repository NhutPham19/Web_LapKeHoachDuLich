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

    def test_travel_time_impacts_slot_capacity_and_item_order(self):
        """Finding #32(a): Thời gian di chuyển cộng vào sức chứa slot, item quá xa làm tràn slot sẽ bị loại."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=2000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        d1 = Destination(
            id=1, name="Điểm Trung Tâm", province="Đà Lạt",
            latitude=11.90, longitude=108.40, category_id=1,
            price_range=1, noise_level=2, duration_hours=2.0,
            is_outdoor=True, opening_hours=None, tags=()
        )
        # d2 cách d1 ~66 km (di chuyển ~2.2h ở 30 km/h). 2.0h + 2.2h + 1.0h = 5.2h > 3.5h morning slot capacity
        d2_far = Destination(
            id=2, name="Điểm Rất Xa", province="Đà Lạt",
            latitude=12.50, longitude=108.40, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.0,
            is_outdoor=True, opening_hours=None, tags=()
        )
        # d3 cách d1 ~1 km (di chuyển ~0.03h). 2.0h + 0.03h + 1.0h = ~3.03h <= 3.5h morning slot capacity
        d3_near = Destination(
            id=3, name="Điểm Gần", province="Đà Lạt",
            latitude=11.91, longitude=108.41, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.0,
            is_outdoor=True, opening_hours=None, tags=()
        )
        ranked = [
            ScoredDestination(destination=d1, score=0.95, cb_score=0.95),
            ScoredDestination(destination=d2_far, score=0.90, cb_score=0.90),
            ScoredDestination(destination=d3_near, score=0.85, cb_score=0.85),
        ]
        day_plans, _ = itinerary.build_itinerary(ranked, req, [])
        morning_items = [it for it in day_plans[0].items if it.time_slot == "morning"]

        # Morning slot chọn d1 và d3_near; d2_far bị loại vì travel_time làm tràn slot
        morning_ids = [it.destination.id for it in morning_items]
        self.assertIn(1, morning_ids)
        self.assertIn(3, morning_ids)
        self.assertNotIn(2, morning_ids)
        # Item thứ 2 phải ghi nhận khoảng cách di chuyển travel_km_from_prev > 0
        self.assertGreater(morning_items[1].travel_km_from_prev, 0.0)

    def test_inter_slot_geographic_continuity(self):
        """Finding #32(b): Liền mạch địa lý giữa các slot — item đầu slot sau ưu tiên điểm gần điểm cuối slot trước."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=2000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        # d_morning chiếm trọn slot sáng (3.5h)
        d_morning = Destination(
            id=1, name="Điểm Sáng", province="Đà Lạt",
            latitude=11.90, longitude=108.40, category_id=1,
            price_range=1, noise_level=2, duration_hours=3.5,
            is_outdoor=True, opening_hours=None, tags=()
        )
        # d_far có điểm cao hơn nhưng ở rất xa d_morning (~66km)
        d_far = Destination(
            id=2, name="Điểm Chiều Xa Điểm Cao", province="Đà Lạt",
            latitude=12.50, longitude=108.40, category_id=1,
            price_range=1, noise_level=2, duration_hours=2.0,
            is_outdoor=True, opening_hours=None, tags=()
        )
        # d_near có điểm thấp hơn chút nhưng rất gần d_morning (~1km)
        d_near = Destination(
            id=3, name="Điểm Chiều Gần Điểm Sáng", province="Đà Lạt",
            latitude=11.91, longitude=108.41, category_id=1,
            price_range=1, noise_level=2, duration_hours=2.0,
            is_outdoor=True, opening_hours=None, tags=()
        )
        ranked = [
            ScoredDestination(destination=d_morning, score=0.98, cb_score=0.98),
            ScoredDestination(destination=d_far, score=0.90, cb_score=0.90),
            ScoredDestination(destination=d_near, score=0.88, cb_score=0.88),
        ]
        day_plans, _ = itinerary.build_itinerary(ranked, req, [])
        afternoon_items = [it for it in day_plans[0].items if it.time_slot == "afternoon"]

        # Item đầu tiên của buổi chiều phải chọn d_near nhờ logic top-M sắp xếp theo khoảng cách tới d_morning
        self.assertTrue(len(afternoon_items) > 0)
        self.assertEqual(afternoon_items[0].destination.id, 3)

    def test_daily_ticket_quota_filters_candidates(self):
        """Finding #32(c): Bộ lọc vé theo ngày allocation['ve_vao_cua'] // days lọc bỏ điểm vượt ngân sách."""
        # 1 người, 1 ngày, ngân sách 1,000,000 VNĐ -> vé vào cửa (10%) là 100,000 VNĐ/ngày
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=1000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        d1 = Destination(
            id=1, name="Điểm Vé Nhẹ", province="Đà Lạt",
            latitude=11.90, longitude=108.40, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.5,
            is_outdoor=True, opening_hours=None, tags=(), ticket_price=40000
        )
        # d2 vé 80,000 -> 40k + 80k = 120k > 100k quota
        d2_expensive = Destination(
            id=2, name="Điểm Vé Đắt", province="Đà Lạt",
            latitude=11.905, longitude=108.405, category_id=1,
            price_range=2, noise_level=2, duration_hours=1.5,
            is_outdoor=True, opening_hours=None, tags=(), ticket_price=80000
        )
        # d3 vé 50,000 -> 40k + 50k = 90k <= 100k quota
        d3_affordable = Destination(
            id=3, name="Điểm Vé Vừa Phải", province="Đà Lạt",
            latitude=11.906, longitude=108.406, category_id=1,
            price_range=2, noise_level=2, duration_hours=1.5,
            is_outdoor=True, opening_hours=None, tags=(), ticket_price=50000
        )
        ranked = [
            ScoredDestination(destination=d1, score=0.95, cb_score=0.95),
            ScoredDestination(destination=d2_expensive, score=0.90, cb_score=0.90),
            ScoredDestination(destination=d3_affordable, score=0.85, cb_score=0.85),
        ]
        day_plans, warnings = itinerary.build_itinerary(ranked, req, [])
        morning_items = [it for it in day_plans[0].items if it.time_slot == "morning"]

        morning_ids = [it.destination.id for it in morning_items]
        self.assertIn(1, morning_ids)
        # d3_affordable được chọn thay vì d2_expensive để không vượt quota vé 100,000 VNĐ
        self.assertIn(3, morning_ids)
        self.assertNotIn(2, morning_ids)

    def test_destination_exceeding_max_slot_capacity_skipped(self):
        """Finding #32(d): Địa điểm có duration_hours > 4.0h vượt sức chứa slot đơn lẻ bị bỏ qua."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=2000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        d_oversized = Destination(
            id=1, name="Điểm Quá Dài 5 Giờ", province="Đà Lạt",
            latitude=11.90, longitude=108.40, category_id=1,
            price_range=1, noise_level=2, duration_hours=5.0,
            is_outdoor=True, opening_hours=None, tags=()
        )
        d_normal = Destination(
            id=2, name="Điểm Bình Thường 2 Giờ", province="Đà Lạt",
            latitude=11.91, longitude=108.41, category_id=1,
            price_range=1, noise_level=2, duration_hours=2.0,
            is_outdoor=True, opening_hours=None, tags=()
        )
        ranked = [
            ScoredDestination(destination=d_oversized, score=0.99, cb_score=0.99),
            ScoredDestination(destination=d_normal, score=0.80, cb_score=0.80),
        ]
        day_plans, _ = itinerary.build_itinerary(ranked, req, [])
        all_ids = [it.destination.id for dp in day_plans for it in dp.items]

        # d_oversized (5.0h) bị bỏ qua, d_normal (2.0h) được xếp vào lịch trình
        self.assertNotIn(1, all_ids)
        self.assertIn(2, all_ids)


if __name__ == "__main__":
    unittest.main()
