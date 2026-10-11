import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.contracts import Destination
from tests.fakes import FakeRepo

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


class SecurityAndEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.destinations = load_fixture_destinations()
        self.repo = FakeRepo(destinations=self.destinations)
        self.app = create_app(repo=self.repo)
        self.app.config["TESTING"] = True
        self.client_a = self.app.test_client()
        self.client_b = self.app.test_client()
        self.client_admin = self.app.test_client()
        self.anon_client = self.app.test_client()

        # Tạo User A (ID = 1)
        self.user_a_id = self._create_user(self.client_a, "user_a@example.com", "passwordA123", "User Alpha")
        # Tạo User B (ID = 2)
        self.user_b_id = self._create_user(self.client_b, "user_b@example.com", "passwordB123", "User Beta")
        # Tạo Admin (ID = 3)
        self.admin_id = self._create_user(self.client_admin, "admin@example.com", "passwordAdmin123", "Quản Trị Viên")
        self.repo.set_user_admin("admin@example.com", is_admin=True)
        with self.client_admin.session_transaction() as sess:
            sess["user"] = dict(sess["user"], is_admin=True)

    def _get_csrf_token(self, client):
        client.get("/")
        with client.session_transaction() as sess:
            return sess.get("csrf_token")

    def _create_user(self, client, email, password, full_name):
        tok = self._get_csrf_token(client)
        client.post("/register", data={
            "email": email,
            "password": password,
            "full_name": full_name,
            "csrf_token": tok,
        })
        with client.session_transaction() as sess:
            return sess["user"]["id"]

    def _create_trip_for_user_a(self):
        tok = self._get_csrf_token(self.client_a)
        vn_today = datetime.now(timezone(timedelta(hours=7))).date()
        valid_date = (vn_today + timedelta(days=2)).isoformat()
        r = self.client_a.post("/trips/new", data={
            "province": "Đà Lạt",
            "start_date": valid_date,
            "days": "2",
            "budget": "2000000",
            "num_people": "2",
            "interests": ["thien_nhien"],
            "travel_style": "tiet_kiem",
            "csrf_token": tok,
        })
        trip_id = int(r.headers["Location"].split("/")[-1])
        return trip_id

    # -------------------------------------------------------------------------
    # 1. Phân quyền & Chống IDOR (Findings #3 & #9)
    # -------------------------------------------------------------------------
    def test_user_b_cannot_access_or_modify_user_a_trip(self):
        """User B không thể đọc, sửa, xóa, chia sẻ hoặc xem candidate trip của User A (trả 404)."""
        trip_a_id = self._create_trip_for_user_a()

        # User B cố đọc trip của A -> 404 (chống dò ID)
        r = self.client_b.get(f"/trips/{trip_a_id}")
        self.assertEqual(r.status_code, 404)

        # User B cố xóa trip của A -> 404
        tok_b = self._get_csrf_token(self.client_b)
        r = self.client_b.post(f"/trips/{trip_a_id}/delete", data={"csrf_token": tok_b})
        self.assertEqual(r.status_code, 404)

        # User B gọi API candidate của A -> 404
        r = self.client_b.get(f"/api/trips/{trip_a_id}/candidates")
        self.assertEqual(r.status_code, 404)

        # User B gọi API chia sẻ trip của A -> 404
        headers_b = {"X-CSRF-Token": tok_b, "Content-Type": "application/json"}
        r = self.client_b.post(f"/api/trips/{trip_a_id}/share", headers=headers_b, json={"is_public": True})
        self.assertEqual(r.status_code, 404)

    def test_admin_route_authorization(self):
        """Chưa đăng nhập chuyển về login; User thường truy cập route admin nhận 403; Admin truy cập thành công."""
        # 1. Chưa đăng nhập
        r_anon = self.anon_client.get("/admin/stats")
        self.assertIn(r_anon.status_code, (302, 401, 403))

        # 2. User thường (User A)
        r_user = self.client_a.get("/admin/stats")
        self.assertEqual(r_user.status_code, 403)

        # 3. Admin thật
        r_admin = self.client_admin.get("/admin/stats")
        self.assertEqual(r_admin.status_code, 200)

    def test_shared_trip_invalid_or_revoked_token_returns_404(self):
        """Link chia sẻ sai token hoặc đã hủy nhận 404."""
        r = self.anon_client.get("/s/non_existent_token_12345")
        self.assertEqual(r.status_code, 404)

    # -------------------------------------------------------------------------
    # 2. CSRF Protection (Finding #2)
    # -------------------------------------------------------------------------
    def test_csrf_token_required_on_state_changing_methods(self):
        """Mọi request POST/PATCH/DELETE thiếu hoặc sai CSRF token đều bị chặn 403."""
        # POST không có CSRF token
        r1 = self.anon_client.post("/login", data={"email": "a@ex.com", "password": "123"})
        self.assertEqual(r1.status_code, 403)

        # POST với CSRF token giả mạo
        r2 = self.anon_client.post("/login", data={
            "email": "a@ex.com",
            "password": "123",
            "csrf_token": "fake_token_malicious",
        })
        self.assertEqual(r2.status_code, 403)

        # API JSON với CSRF token sai
        trip_a_id = self._create_trip_for_user_a()
        r3 = self.client_a.post(
            f"/api/trips/{trip_a_id}/share",
            headers={"X-CSRF-Token": "bad_token", "Content-Type": "application/json"},
            json={"is_public": True},
        )
        self.assertEqual(r3.status_code, 403)

    # -------------------------------------------------------------------------
    # 3. XSS Escaping & Script Injection (Finding #7)
    # -------------------------------------------------------------------------
    def test_xss_payload_in_user_inputs_escaped(self):
        """Chuỗi chứa <script> trong full_name không được render dưới dạng script thực thi."""
        xss_name = "User <script>alert('xss')</script>"
        client_xss = self.app.test_client()
        tok = self._get_csrf_token(client_xss)
        client_xss.post("/register", data={
            "email": "xss_user@example.com",
            "password": "password123",
            "full_name": xss_name,
            "csrf_token": tok,
        })
        # Xem trang index hoặc trips
        r = client_xss.get("/trips")
        self.assertEqual(r.status_code, 200)
        # HTML phải escape hoặc không chứa thẻ script thô nguyên vẹn có thể thực thi
        self.assertNotIn("<script>alert('xss')</script>", r.get_data(as_text=True))

    # -------------------------------------------------------------------------
    # 4. SQL Injection Resilience
    # -------------------------------------------------------------------------
    def test_sql_injection_resilience_in_inputs(self):
        """Các chuỗi SQL injection (' OR 1=1 --) trong email và tên không gây crash hay bypass xác thực."""
        tok = self._get_csrf_token(self.anon_client)
        sqli_payload = "admin' OR 1=1 --"
        r = self.anon_client.post("/login", data={
            "email": sqli_payload,
            "password": "any_password",
            "csrf_token": tok,
        })
        # Phải trả về 400 và không đăng nhập được
        self.assertEqual(r.status_code, 400)
        with self.anon_client.session_transaction() as sess:
            self.assertNotIn("user", sess)

    # -------------------------------------------------------------------------
    # 5. Password Security & Hash Privacy
    # -------------------------------------------------------------------------
    def test_password_never_leaked_in_plain_text_or_responses(self):
        """Mật khẩu thô không bao giờ được lưu trong repo và hash không bao giờ bị lộ ra ngoài giao diện."""
        user = self.repo.get_user(self.user_a_id)
        self.assertNotIn("password", user)
        self.assertTrue(user["password_hash"].startswith("scrypt:") or user["password_hash"].startswith("pbkdf2:"))
        self.assertNotEqual(user["password_hash"], "passwordA123")

        # Kiểm tra trang profile / trips không in hash
        r = self.client_a.get("/trips")
        self.assertNotIn(user["password_hash"], r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
