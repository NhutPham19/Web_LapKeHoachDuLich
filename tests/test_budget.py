import unittest
from datetime import date

from app.contracts import CostBreakdown, DayPlan, Destination, ItineraryItem, TripRequest
from app.services import budget


class BudgetServiceTests(unittest.TestCase):
    def test_allocation_sum_equals_budget_even_for_odd_amounts(self):
        """sum(allocation.values()) luôn bằng chính xác budget, kể cả số tiền lẻ không chia hết."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=3,
            budget=1234567,  # Ngân sách lẻ
            num_people=2,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        cost = budget.allocate(req, ())
        self.assertEqual(sum(cost.allocation.values()), req.budget)

        # Thử thêm ngân sách 5,555,555
        req2 = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=4,
            budget=5555555,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="thoai_mai",
        )
        cost2 = budget.allocate(req2, ())
        self.assertEqual(sum(cost2.allocation.values()), req2.budget)

    def test_per_day_and_per_day_allocation(self):
        """Finding #18: per_day và per_day_allocation được tính chính xác bằng phép chia nguyên cho days."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=3,
            budget=3000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        cost = budget.allocate(req, ())
        self.assertEqual(cost.per_day, 1000000)
        self.assertIn("ve_vao_cua", cost.per_day_allocation)
        for cat, amt in cost.allocation.items():
            self.assertEqual(cost.per_day_allocation[cat], amt // 3)

    def test_within_budget_calculation(self):
        """within_budget là True nếu tổng vé <= định mức vé vào cửa, ngược lại là False."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=2000000,  # 10% vé vào cửa = 200,000 VNĐ
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        dummy_dest = Destination(
            id=1, name="Điểm A", province="Đà Lạt",
            latitude=11.9, longitude=108.4, category_id=1,
            price_range=1, noise_level=2, duration_hours=1.5,
            is_outdoor=True, tags=()
        )

        # Trường hợp 1: Tổng vé 150,000 <= 200,000 -> True
        item_cheap = ItineraryItem(
            destination=dummy_dest, day_number=1, time_slot="morning",
            order_in_slot=1, estimated_cost=150000, notes="", travel_km_from_prev=0.0
        )
        day_cheap = DayPlan(day_number=1, date=date(2026, 11, 1), items=(item_cheap,), weather=None)
        cost_cheap = budget.allocate(req, (day_cheap,))
        self.assertTrue(cost_cheap.within_budget)
        self.assertEqual(cost_cheap.tickets_estimated, 150000)

        # Trường hợp 2: Tổng vé 350,000 > 200,000 -> False
        item_expensive = ItineraryItem(
            destination=dummy_dest, day_number=1, time_slot="morning",
            order_in_slot=1, estimated_cost=350000, notes="", travel_km_from_prev=0.0
        )
        day_expensive = DayPlan(day_number=1, date=date(2026, 11, 1), items=(item_expensive,), weather=None)
        cost_expensive = budget.allocate(req, (day_expensive,))
        self.assertFalse(cost_expensive.within_budget)
        self.assertEqual(cost_expensive.tickets_estimated, 350000)


if __name__ == "__main__":
    unittest.main()
