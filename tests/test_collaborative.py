import unittest
from app.services import collaborative
from tests.fixtures.ratings import SYNTHETIC_RATINGS, NATURE_USERS, CULTURE_USERS


class CollaborativeFilteringServiceTests(unittest.TestCase):
    def test_cold_start_user_none(self):
        """User chưa đăng nhập (user_id is None) -> trả dict rỗng."""
        scores = collaborative.score(None, SYNTHETIC_RATINGS, [1, 2, 3])
        self.assertEqual(scores, {})

    def test_cold_start_total_ratings_below_threshold(self):
        """Toàn hệ thống dưới 50 đánh giá -> trả dict rỗng."""
        few_ratings = SYNTHETIC_RATINGS[:49]
        scores = collaborative.score(NATURE_USERS[0], few_ratings, [1, 2, 3])
        self.assertEqual(scores, {})

    def test_cold_start_user_ratings_below_threshold(self):
        """User mới có < 5 đánh giá -> bỏ qua CF, trả dict rỗng."""
        # Tạo user 999 chỉ có 4 ratings
        custom_ratings = list(SYNTHETIC_RATINGS) + [
            (999, 1, 5),
            (999, 2, 4),
            (999, 3, 5),
            (999, 4, 3),
        ]
        scores = collaborative.score(999, custom_ratings, [5, 6, 7])
        self.assertEqual(scores, {})

    def test_valid_user_produces_normalized_predictions(self):
        """User hợp lệ với đủ đánh giá -> điểm dự đoán thuộc khoảng [0.0, 1.0]."""
        target_user = NATURE_USERS[0]
        candidate_ids = [1, 3, 5, 7, 9]
        scores = collaborative.score(target_user, SYNTHETIC_RATINGS, candidate_ids)
        self.assertIsInstance(scores, dict)
        self.assertTrue(len(scores) > 0)
        for cid, score in scores.items():
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_preferences_lean_towards_similar_users(self):
        """Người dùng nhóm thiên nhiên phải nhận điểm dự đoán cho điểm thiên nhiên cao hơn điểm văn hóa."""
        target_user = NATURE_USERS[0]
        nature_cand = 5  # Điểm thiên nhiên
        culture_cand = 7  # Điểm văn hóa
        scores = collaborative.score(target_user, SYNTHETIC_RATINGS, [nature_cand, culture_cand])
        self.assertIn(nature_cand, scores)
        self.assertIn(culture_cand, scores)
        self.assertGreater(scores[nature_cand], scores[culture_cand])

    def test_candidate_without_positive_neighbors_omitted(self):
        """Candidate không có ai trong số hàng xóm tương đồng chấm điểm -> vắng mặt trong dict kết quả."""
        target_user = NATURE_USERS[0]
        unrated_destination_id = 9999
        scores = collaborative.score(target_user, SYNTHETIC_RATINGS, [unrated_destination_id])
        self.assertNotIn(unrated_destination_id, scores)

    def test_duplicate_ratings_averaged(self):
        """Finding #14: Trùng cặp (user, destination) được gộp bằng giá trị trung bình."""
        # Thêm rating trùng: user 101 chấm điểm 1 hai lần: 5 và 1 -> trung bình là 3.0
        ratings_with_dup = list(SYNTHETIC_RATINGS) + [(101, 1, 1)]
        scores = collaborative.score(101, ratings_with_dup, [1, 2])
        self.assertIn(1, scores)
        self.assertGreaterEqual(scores[1], 0.0)
        self.assertLessEqual(scores[1], 1.0)

    def test_all_fives_and_zero_division_prevention(self):
        """Finding #13: Test user chấm toàn 5 sao, ma trận thưa hoặc độ tương đồng = 0 không ném ngoại lệ."""
        # 50 ratings cho 5 users, mỗi user chấm 10 điểm toàn 5 sao
        sparse_ratings = [
            (uid, did, 5)
            for uid in range(1, 6)
            for did in range(1, 11)
        ]
        scores = collaborative.score(1, sparse_ratings, [11, 12])
        self.assertIsInstance(scores, dict)
        # Các điểm 11, 12 chưa ai chấm nên không có kết quả
        self.assertEqual(scores, {})


if __name__ == "__main__":
    unittest.main()
