import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.contracts import (
    CostBreakdown,
    DayPlan,
    Destination,
    ItineraryItem,
    TripPlan,
    TripRequest,
)
from app.db import PgRepo

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DB_URL, "Bỏ qua vì không có biến môi trường TEST_DATABASE_URL (Finding #27)")
class PostgresIntegrationTests(unittest.TestCase):
    """
    Test tích hợp thật với PostgreSQL / Supabase dev (Finding #27).
    Chỉ thực thi khi có TEST_DATABASE_URL.
    """

    @classmethod
    def setUpClass(cls):
        import psycopg2
        cls.conn = psycopg2.connect(TEST_DB_URL)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            cur.execute(schema_sql)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "conn") and cls.conn:
            cls.conn.close()

    def setUp(self):
        self.repo = PgRepo(db_url=TEST_DB_URL)
        import psycopg2
        self.test_conn = psycopg2.connect(TEST_DB_URL)
        self.test_conn.autocommit = False

    def tearDown(self):
        self.test_conn.rollback()
        self.test_conn.close()
        # Dọn dẹp dữ liệu test mẫu
        with self.repo._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ratings WHERE review_text LIKE 'test_pg_%'")
                cur.execute("DELETE FROM trips WHERE title LIKE 'test_pg_%'")
                cur.execute("DELETE FROM destinations WHERE name LIKE 'test_pg_%'")
                cur.execute("DELETE FROM users WHERE email LIKE 'test_pg_%'")
                cur.execute("DELETE FROM weather_cache WHERE province LIKE 'test_pg_%'")

    def test_schema_idempotence(self):
        """Kiểm tra schema.sql có thể chạy lặp lại 2 lần mà không phát sinh lỗi."""
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        with self.test_conn.cursor() as cur:
            cur.execute(schema_sql)
            cur.execute(schema_sql)
        self.test_conn.commit()

    def test_user_crud_and_preferences(self):
        """Kiểm tra tạo user, lấy user theo email/id, và lưu user_preferences."""
        email = f"test_pg_user_{datetime.now().timestamp()}@example.com"
        pwd_hash = "scrypt:32768:8:1$test$fakehash"
        name = "Test PG User"

        user_id = self.repo.create_user(email, pwd_hash, name)
        self.assertIsInstance(user_id, int)

        user_by_email = self.repo.get_user_by_email(email)
        self.assertIsNotNone(user_by_email)
        self.assertEqual(user_by_email["id"], user_id)
        self.assertEqual(user_by_email["full_name"], name)

        user_by_id = self.repo.get_user(user_id)
        self.assertIsNotNone(user_by_id)
        self.assertEqual(user_by_id["email"], email)

        # Lưu sở thích
        interests = ("thien_nhien", "van_hoa")
        self.repo.save_preferences(user_id, interests, "thoai_mai")
        prefs = self.repo.get_preferences(user_id)
        self.assertIn("thien_nhien", prefs["interests"])
        self.assertIn("van_hoa", prefs["interests"])
        self.assertEqual(prefs["travel_style"], "thoai_mai")

    def test_destination_soft_delete(self):
        """Kiểm tra xóa mềm địa điểm qua cột is_active (Finding #23)."""
        with self.repo._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO destinations (name, province, address, latitude, longitude,
                                            price_range, noise_level, duration_hours, is_outdoor, ticket_price, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    RETURNING id
                    """,
                    ("test_pg_dest_active", "Đà Lạt", "Test Address", 11.9, 108.4, 2, 2, 1.5, True, 50000),
                )
                dest_id = cur.fetchone()[0]

        # Kiểm tra trước khi xóa mềm
        active_list = self.repo.list_destinations("Đà Lạt", active_only=True)
        self.assertTrue(any(d.id == dest_id for d in active_list))

        # Thực hiện xóa mềm
        self.repo.delete_destination(dest_id)

        # Sau khi xóa mềm: active_only=True không thấy, nhưng get_destination vẫn đọc được
        active_after = self.repo.list_destinations("Đà Lạt", active_only=True)
        self.assertFalse(any(d.id == dest_id for d in active_after))

        dest_obj = self.repo.get_destination(dest_id)
        self.assertIsNotNone(dest_obj)
        self.assertFalse(dest_obj.is_active)

    def test_trip_persistence_jsonb_columns(self):
        """Kiểm tra lưu trip với cột JSONB interests và warnings (Finding #20)."""
        email = f"test_pg_trip_{datetime.now().timestamp()}@example.com"
        user_id = self.repo.create_user(email, "hash", "Trip Owner")

        # Tạo điểm đến mẫu
        with self.repo._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO destinations (name, province, address, latitude, longitude,
                                            price_range, noise_level, duration_hours, is_outdoor, ticket_price, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    RETURNING id
                    """,
                    ("test_pg_dest_trip", "Đà Lạt", "123 Đường Test", 11.94, 108.43, 2, 2, 1.5, True, 20000),
                )
                dest_id = cur.fetchone()[0]

        dest = self.repo.get_destination(dest_id)
        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 12, 1),
            days=1,
            budget=2000000,
            num_people=2,
            interests=("am_thuc", "check_in"),
            travel_style="tiet_kiem",
            user_id=user_id,
        )
        item = ItineraryItem(
            destination=dest,
            day_number=1,
            time_slot="morning",
            order_in_slot=1,
            estimated_cost=40000,
            travel_km_from_prev=0.0,
            notes="",
        )
        day_plan = DayPlan(day_number=1, date=date(2026, 12, 1), items=(item,), weather=None)
        cost = CostBreakdown(
            total_budget=2000000,
            per_day=2000000,
            allocation={"an_uong": 600000, "luu_tru": 700000, "di_chuyen": 300000, "ve_vao_cua": 200000, "du_phong": 200000},
            tickets_estimated=40000,
            within_budget=True,
        )
        sample_warnings = ["Cảnh báo thời tiết test_pg", "Lưu ý di chuyển test_pg"]
        plan = TripPlan(request=req, days=(day_plan,), cost=cost, warnings=sample_warnings)

        trip_id = self.repo.save_trip(user_id, "test_pg_trip_title", plan)
        self.assertIsInstance(trip_id, int)

        loaded_trip = self.repo.get_trip(trip_id)
        self.assertIsNotNone(loaded_trip)
        self.assertEqual(loaded_trip.title, "test_pg_trip_title")
        self.assertIn("am_thuc", loaded_trip.plan.request.interests)
        self.assertIn("check_in", loaded_trip.plan.request.interests)
        self.assertEqual(loaded_trip.plan.warnings, sample_warnings)

    def test_ratings_unique_constraint_and_upsert(self):
        """Kiểm tra UNIQUE(user_id, trip_id, destination_id) và UPSERT reset is_approved (Finding #4)."""
        email = f"test_pg_rating_{datetime.now().timestamp()}@example.com"
        user_id = self.repo.create_user(email, "hash", "Rating Tester")

        with self.repo._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO destinations (name, province, address, latitude, longitude,
                                            price_range, noise_level, duration_hours, is_outdoor, ticket_price, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    RETURNING id
                    """,
                    ("test_pg_dest_rate", "Đà Lạt", "Test", 11.9, 108.4, 1, 1, 1.0, True, 0),
                )
                dest_id = cur.fetchone()[0]

        # 1. Tạo đánh giá lần đầu
        r1_id = self.repo.save_rating(user_id, dest_id, None, 4, "test_pg_rev1")
        # Quản trị viên duyệt
        self.repo.approve_rating(r1_id)
        approved = self.repo.list_approved_ratings()
        self.assertTrue(any(u == user_id and d == dest_id and s == 4 for u, d, s in approved))

        # 2. Gửi lại đánh giá mới cho cùng địa điểm -> UPSERT, không tạo bản ghi mới, reset is_approved=False
        r2_id = self.repo.save_rating(user_id, dest_id, None, 5, "test_pg_rev2")
        self.assertEqual(r1_id, r2_id)  # Cùng id dòng

        # Sau khi sửa đánh giá, chưa được duyệt lại -> không nằm trong danh sách approved
        approved_after = self.repo.list_approved_ratings()
        self.assertFalse(any(u == user_id and d == dest_id for u, d, s in approved_after))

        # Nằm trong danh sách pending với điểm mới là 5
        pending = self.repo.list_pending_ratings()
        matching = [p for p in pending if p["id"] == r1_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["score"], 5)
        self.assertEqual(matching[0]["review_text"], "test_pg_rev2")

    def test_weather_cache_single_row_per_province(self):
        """Kiểm tra cache thời tiết chỉ lưu đúng một dòng duy nhất cho mỗi tỉnh (Finding #16)."""
        prov = f"test_pg_prov_{int(datetime.now().timestamp())}"
        data1 = [{"date": "2026-10-15", "temp_min": 18, "temp_max": 25}]
        data2 = [{"date": "2026-10-15", "temp_min": 20, "temp_max": 27}]

        self.repo.put_weather_cache(prov, data1)
        cached = self.repo.get_weather_cache(prov, max_age_seconds=3600)
        self.assertEqual(cached, data1)

        # Ghi đè lần 2
        self.repo.put_weather_cache(prov, data2)
        cached2 = self.repo.get_weather_cache(prov, max_age_seconds=3600)
        self.assertEqual(cached2, data2)

        # Kiểm tra số dòng thực tế trong DB
        with self.repo._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM weather_cache WHERE province = %s", (prov,))
                count = cur.fetchone()[0]
                self.assertEqual(count, 1)

    def test_trip_share_token_reset(self):
        """Kiểm tra bật chia sẻ cấp token mới, tắt chia sẻ cập nhật share_token về NULL (Finding #8)."""
        email = f"test_pg_share_{datetime.now().timestamp()}@example.com"
        user_id = self.repo.create_user(email, "hash", "Share Tester")

        req = TripRequest(
            province="Đà Lạt",
            start_date=date(2026, 12, 1),
            days=1,
            budget=2000000,
            num_people=2,
            interests=("am_thuc",),
            travel_style="tiet_kiem",
            user_id=user_id,
        )
        day_plan = DayPlan(day_number=1, date=date(2026, 12, 1), items=(), weather=None)
        cost = CostBreakdown(
            total_budget=2000000,
            per_day=2000000,
            allocation={},
            tickets_estimated=0,
            within_budget=True,
        )
        plan = TripPlan(request=req, days=(day_plan,), cost=cost)
        trip_id = self.repo.save_trip(user_id, "test_pg_share_title", plan)

        # Bật chia sẻ
        tok1 = self.repo.set_sharing(trip_id, True)
        self.assertIsNotNone(tok1)
        trip_shared = self.repo.get_trip(trip_id)
        self.assertTrue(trip_shared.is_public)
        self.assertEqual(trip_shared.share_token, tok1)

        # Tắt chia sẻ
        tok2 = self.repo.set_sharing(trip_id, False)
        self.assertIsNone(tok2)
        trip_unshared = self.repo.get_trip(trip_id)
        self.assertFalse(trip_unshared.is_public)
        self.assertIsNone(trip_unshared.share_token)


if __name__ == "__main__":
    unittest.main()
