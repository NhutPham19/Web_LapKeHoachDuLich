import unittest
from datetime import date
from app.contracts import Destination, TripRequest, INTERESTS
from app.services import content_based


class ContentBasedServiceTests(unittest.TestCase):
    def setUp(self):
        self.d_nature = Destination(
            id=1,
            name="Rừng Thông Bản Giả",
            province="Đà Lạt",
            latitude=11.9,
            longitude=108.4,
            category_id=1,
            price_range=1,
            noise_level=1,
            duration_hours=2.0,
            is_outdoor=True,
            tags=("thien_nhien", "nui"),
        )
        self.d_food = Destination(
            id=2,
            name="Phố Ẩm Thực Chợ Giả",
            province="Đà Lạt",
            latitude=11.95,
            longitude=108.45,
            category_id=2,
            price_range=3,
            noise_level=4,
            duration_hours=1.5,
            is_outdoor=False,
            tags=("am_thuc", "mua_sam"),
        )
        self.d_zero_tags = Destination(
            id=3,
            name="Điểm Không Gắn Thẻ",
            province="Đà Lạt",
            latitude=11.92,
            longitude=108.42,
            category_id=3,
            price_range=2,
            noise_level=3,
            duration_hours=1.0,
            is_outdoor=True,
            tags=(),
        )

    def test_cosine_similarity_manual_calculation(self):
        # User thích ('thien_nhien', 'bien') -> vector có 2 phần tử 1.0, norm = sqrt(2)
        # d_nature có ('thien_nhien', 'nui') -> vector có 2 phần tử 1.0, norm = sqrt(2)
        # Dot product = 1.0 -> Cosine = 1 / (sqrt(2) * sqrt(2)) = 0.5
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien", "bien"),
            travel_style="tiet_kiem",
        )
        scores = content_based.score(req, [self.d_nature])
        # STYLE_PRICE_TARGET['tiet_kiem'] = 2; price_range = 1 -> price_fit = 1 - abs(1-2)/3 = 2/3
        # không có yen_tinh -> target 3, noise = 1 -> noise_fit = 1 - abs(1-3)/4 = 0.5
        # cb = 0.7 * 0.5 + 0.15 * (2/3) + 0.15 * 0.5 = 0.35 + 0.10 + 0.075 = 0.525
        self.assertAlmostEqual(scores[1], 0.525, places=4)

    def test_zero_vector_returns_zero_cosine(self):
        # Điểm không có tag nào -> cosine = 0.0
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="thoai_mai",
        )
        scores = content_based.score(req, [self.d_zero_tags])
        # Cosine = 0.0
        # STYLE_PRICE_TARGET['thoai_mai'] = 3; price_range = 2 -> price_fit = 1 - abs(2-3)/3 = 2/3
        # noise = 3 với target 3 -> noise_fit = 1.0
        # cb = 0.7 * 0.0 + 0.15 * (2/3) + 0.15 * 1.0 = 0.10 + 0.15 = 0.25
        self.assertAlmostEqual(scores[3], 0.25, places=4)

    def test_different_interests_produce_different_rankings(self):
        # User A thích thiên nhiên
        req_nature = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="thoai_mai",
        )
        scores_nature = content_based.score(req_nature, [self.d_nature, self.d_food])
        self.assertGreater(scores_nature[1], scores_nature[2], "Khách thích thiên nhiên phải chấm điểm rừng thông cao hơn")

        # User B thích ẩm thực
        req_food = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("am_thuc",),
            travel_style="thoai_mai",
        )
        scores_food = content_based.score(req_food, [self.d_nature, self.d_food])
        self.assertGreater(scores_food[2], scores_food[1], "Khách thích ẩm thực phải chấm điểm ẩm thực cao hơn")

    def test_price_fit_monotone_for_travel_styles(self):
        # 4 địa điểm giống nhau về tags nhưng khác price_range (1, 2, 3, 4)
        dests = [
            Destination(
                id=i,
                name=f"Điểm {i}",
                province="Đà Lạt",
                latitude=11.9,
                longitude=108.4,
                category_id=1,
                price_range=i,
                noise_level=3,
                duration_hours=1.5,
                is_outdoor=True,
                tags=("thien_nhien",),
            )
            for i in range(1, 5)
        ]

        # Khách tiết kiệm (STYLE_PRICE_TARGET = 2): price 2 tối ưu, price 1 & 3 bằng nhau, price 4 thấp nhất
        req_budget = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=1000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        scores_budget = content_based.score(req_budget, dests)
        self.assertGreater(scores_budget[2], scores_budget[1])
        self.assertEqual(scores_budget[1], scores_budget[3])
        self.assertGreater(scores_budget[3], scores_budget[4])

        # Khách sang trọng (STYLE_PRICE_TARGET = 4): price 4 > 3 > 2 > 1
        req_luxury = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=10000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="sang_trong",
        )
        scores_luxury = content_based.score(req_luxury, dests)
        self.assertGreater(scores_luxury[4], scores_luxury[3])
        self.assertGreater(scores_luxury[3], scores_luxury[2])
        self.assertGreater(scores_luxury[2], scores_luxury[1])


if __name__ == "__main__":
    unittest.main()
