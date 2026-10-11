import unittest
from datetime import date
from unittest.mock import patch

from app.contracts import Destination, TripRequest
from app.services import recommender
from tests.fixtures.ratings import SYNTHETIC_RATINGS, NATURE_USERS


class RecommenderServiceTests(unittest.TestCase):
    def setUp(self):
        self.d_dalat_1 = Destination(
            id=1,
            name="Rừng Thông Đà Lạt 1",
            province="Đà Lạt",
            latitude=11.9,
            longitude=108.4,
            category_id=1,
            price_range=2,
            noise_level=2,
            duration_hours=2.0,
            is_outdoor=True,
            tags=("thien_nhien",),
        )
        self.d_dalat_2 = Destination(
            id=2,
            name="Vườn Hoa Đà Lạt 2",
            province="Đà Lạt",
            latitude=11.92,
            longitude=108.42,
            category_id=1,
            price_range=2,
            noise_level=2,
            duration_hours=2.0,
            is_outdoor=True,
            tags=("thien_nhien",),
        )
        self.d_hoian = Destination(
            id=3,
            name="Phố Cổ Hội An",
            province="Hội An",
            latitude=15.88,
            longitude=108.33,
            category_id=2,
            price_range=2,
            noise_level=3,
            duration_hours=2.0,
            is_outdoor=False,
            tags=("van_hoa",),
        )

    def test_filter_by_province_only(self):
        """Recommender chỉ trả về các địa điểm thuộc cùng tỉnh với request."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        res = recommender.recommend(req, [self.d_dalat_1, self.d_hoian], SYNTHETIC_RATINGS)
        returned_ids = [item.destination.id for item in res]
        self.assertIn(1, returned_ids)
        self.assertNotIn(3, returned_ids)

    def test_empty_destinations_returns_empty_list(self):
        """Không có điểm đến nào trong tỉnh -> trả về danh sách rỗng."""
        req = TripRequest(
            province="Phú Quốc",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
        )
        res = recommender.recommend(req, [self.d_dalat_1, self.d_hoian], SYNTHETIC_RATINGS)
        self.assertEqual(res, [])

    def test_no_cf_score_when_cold_start(self):
        """Khi user_id is None hoặc cold-start, cf_score = None và final_score là cb normalized."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
            user_id=None,
        )
        res = recommender.recommend(req, [self.d_dalat_1, self.d_dalat_2], [])
        for item in res:
            self.assertIsNone(item.cf_score)
            self.assertIsNotNone(item.cb_score)
            self.assertEqual(item.score, 1.0)

    def test_hybrid_formula_weights(self):
        """Khi có cả CB và CF, điểm cuối cùng là 0.7 * cb_norm + 0.3 * cf_norm."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="thoai_mai",
            user_id=10,
        )
        with patch("app.services.content_based.score") as mock_cb, \
             patch("app.services.collaborative.score") as mock_cf:
            # Giả lập cb_scores: điểm 1 là 0.8, điểm 2 là 0.4 -> sau min-max: điểm 1 là 1.0, điểm 2 là 0.0
            mock_cb.return_value = {1: 0.8, 2: 0.4}
            # Giả lập cf_scores: điểm 1 là 0.2, điểm 2 là 0.6 -> sau min-max: điểm 1 là 0.0, điểm 2 là 1.0
            mock_cf.return_value = {1: 0.2, 2: 0.6}

            res = recommender.recommend(req, [self.d_dalat_1, self.d_dalat_2], [])
            res_dict = {item.destination.id: item for item in res}

            # Điểm 1: 0.7 * 1.0 + 0.3 * 0.0 = 0.70
            self.assertAlmostEqual(res_dict[1].score, 0.7, places=4)
            self.assertAlmostEqual(res_dict[1].cb_score, 0.8, places=4)
            self.assertAlmostEqual(res_dict[1].cf_score, 0.2, places=4)

            # Điểm 2: 0.7 * 0.0 + 0.3 * 1.0 = 0.30
            self.assertAlmostEqual(res_dict[2].score, 0.3, places=4)
            self.assertAlmostEqual(res_dict[2].cb_score, 0.4, places=4)
            self.assertAlmostEqual(res_dict[2].cf_score, 0.6, places=4)

    def test_tie_breaking_by_id_ascending(self):
        """Khi hòa điểm, điểm có id nhỏ hơn sẽ được xếp trước."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
            user_id=None,
        )
        # Cả d_dalat_1 và d_dalat_2 đều có cùng thuộc tính tags, price, noise
        res = recommender.recommend(req, [self.d_dalat_2, self.d_dalat_1], [])
        self.assertEqual(len(res), 2)
        self.assertAlmostEqual(res[0].score, res[1].score)
        # ID 1 phải đứng trước ID 2
        self.assertEqual(res[0].destination.id, 1)
        self.assertEqual(res[1].destination.id, 2)

    def test_min_max_branch_max_equals_min(self):
        """Finding #31: Khi mọi candidate bằng điểm CB (max == min), không chia cho 0, trả về 1.0."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
            user_id=None,
        )
        with patch("app.services.content_based.score") as mock_cb:
            mock_cb.return_value = {1: 0.65, 2: 0.65}
            res = recommender.recommend(req, [self.d_dalat_1, self.d_dalat_2], [])
            self.assertEqual(len(res), 2)
            self.assertEqual(res[0].score, 1.0)
            self.assertEqual(res[1].score, 1.0)

    def test_min_max_single_candidate(self):
        """Finding #31: Khi chỉ có 1 candidate duy nhất, max == min, trả về 1.0 mà không chia cho 0."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=1,
            budget=1000000,
            num_people=1,
            interests=("thien_nhien",),
            travel_style="tiet_kiem",
            user_id=None,
        )
        with patch("app.services.content_based.score") as mock_cb:
            mock_cb.return_value = {1: 0.8}
            res = recommender.recommend(req, [self.d_dalat_1], [])
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0].score, 1.0)

    def test_cf_min_max_restricted_to_scored_items(self):
        """Finding #31: CF chỉ min-max trong tập có điểm CF, item không có CF giữ cf_score=None."""
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 11, 1),
            days=2,
            budget=2000000,
            num_people=2,
            interests=("thien_nhien",),
            travel_style="thoai_mai",
            user_id=10,
        )
        d_dalat_3 = Destination(
            id=4,
            name="Thác Datanla 4",
            province="Đà Lạt",
            latitude=11.91,
            longitude=108.44,
            category_id=1,
            price_range=2,
            noise_level=2,
            duration_hours=2.0,
            is_outdoor=True,
            tags=("thien_nhien",),
        )
        with patch("app.services.content_based.score") as mock_cb, \
             patch("app.services.collaborative.score") as mock_cf:
            # CB cho cả 3 điểm: 1, 2, 4
            mock_cb.return_value = {1: 0.8, 2: 0.6, 4: 0.4}
            # CF chỉ có điểm cho 1 và 2 (điểm 4 không có CF)
            mock_cf.return_value = {1: 3.0, 2: 5.0}

            res = recommender.recommend(req, [self.d_dalat_1, self.d_dalat_2, d_dalat_3], [])
            res_dict = {item.destination.id: item for item in res}

            # Điểm 4 không có CF -> cf_score is None, score = cb_norm (0.0 vì min_cb=0.4)
            self.assertIsNone(res_dict[4].cf_score)
            self.assertAlmostEqual(res_dict[4].score, 0.0, places=4)

            # Điểm 1 và 2 có CF: min_cf = 3.0, max_cf = 5.0
            # Điểm 1: cb_norm = 1.0, cf_norm = 0.0 -> score = 0.7 * 1.0 + 0.3 * 0.0 = 0.7
            self.assertAlmostEqual(res_dict[1].score, 0.7, places=4)
            # Điểm 2: cb_norm = 0.5, cf_norm = 1.0 -> score = 0.7 * 0.5 + 0.3 * 1.0 = 0.65
            self.assertAlmostEqual(res_dict[2].score, 0.65, places=4)


if __name__ == "__main__":
    unittest.main()
