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

    def _create_trip(self, client):
        tok = self._get_csrf_token(client)
        vn_today = datetime.now(timezone(timedelta(hours=7))).date()
        valid_date = (vn_today + timedelta(days=2)).isoformat()
        r = client.post("/trips/new", data={
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

    def _create_trip_for_user_a(self):
        return self._create_trip(self.client_a)

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

    # -------------------------------------------------------------------------
    # 6. IDOR & Integrity sâu (Finding #33)
    # -------------------------------------------------------------------------
    def test_cross_trip_item_idor_and_whitelist_columns(self):
        """Finding #3 & #33: Không thể sửa/xóa item của trip khác, khóa ngoài whitelist bị bỏ qua, chặn sai tỉnh/ngày."""
        trip_a_id = self._create_trip_for_user_a()
        trip_b_id = self._create_trip(self.client_b)

        trip_a = self.repo.get_trip(trip_a_id)
        trip_b = self.repo.get_trip(trip_b_id)
        item_a = trip_a.plan.days[0].items[0]
        item_b = trip_b.plan.days[0].items[0]

        tok_a = self._get_csrf_token(self.client_a)
        headers_a = {"X-CSRF-Token": tok_a, "Content-Type": "application/json"}

        # 1. User A cố update item của Trip B qua endpoint trip của mình -> 404
        r = self.client_a.patch(f"/api/trips/{trip_a_id}/items/{item_b.id}", headers=headers_a, json={"notes": "Hacked"})
        self.assertEqual(r.status_code, 404)

        # 2. User A cố delete item của Trip B qua endpoint trip của mình -> 404
        r = self.client_a.delete(f"/api/trips/{trip_a_id}/items/{item_b.id}", headers=headers_a)
        self.assertEqual(r.status_code, 404)

        # 3. Payload chứa các key ngoài whitelist (id, trip_id, is_active) không được ghi đè
        r = self.client_a.patch(
            f"/api/trips/{trip_a_id}/items/{item_a.id}",
            headers=headers_a,
            json={"id": 99999, "trip_id": 88888, "is_active": False, "notes": "Ghi chú hợp lệ"},
        )
        self.assertEqual(r.status_code, 200)
        reloaded_trip_a = self.repo.get_trip(trip_a_id)
        reloaded_item = [it for day in reloaded_trip_a.plan.days for it in day.items if it.id == item_a.id][0]
        self.assertEqual(reloaded_item.notes, "Ghi chú hợp lệ")
        self.assertEqual(reloaded_item.id, item_a.id)

        # 4. Sửa destination_id sang một điểm khác tỉnh (Hội An trong fixture) -> 400
        hoian_dest = next(d for d in self.destinations if d.province == "Hội An")
        r = self.client_a.patch(
            f"/api/trips/{trip_a_id}/items/{item_a.id}",
            headers=headers_a,
            json={"destination_id": hoian_dest.id},
        )
        self.assertEqual(r.status_code, 400)

        # 5. Sửa day_number ngoài 1..total_days -> 400
        r = self.client_a.patch(
            f"/api/trips/{trip_a_id}/items/{item_a.id}",
            headers=headers_a,
            json={"day_number": 99},
        )
        self.assertEqual(r.status_code, 400)

    def test_rating_membership_duplicate_and_unapprove_on_edit(self):
        """Finding #4 & #33: Rating cho điểm không thuộc trip bị chặn 400, gửi lại không nhân đôi, sửa rating reset is_approved=False."""
        trip_a_id = self._create_trip_for_user_a()
        tok_a = self._get_csrf_token(self.client_a)

        trip_a = self.repo.get_trip(trip_a_id)
        valid_dest_id = trip_a.plan.days[0].items[0].destination.id
        foreign_dest_id = next(d.id for d in self.destinations if d.id != valid_dest_id and d.province == "Hội An")

        self.repo.set_status(trip_a_id, "completed")
        with patch("app.routes.ratings.today_vn", return_value=date(2026, 12, 10)):
            # 1. Rating cho địa điểm không thuộc trip -> 400
            r_foreign = self.client_a.post(
                f"/trips/{trip_a_id}/rate",
                data={
                    f"score_{foreign_dest_id}": "5",
                    "csrf_token": tok_a,
                },
            )
            self.assertEqual(r_foreign.status_code, 400)

            # 2. Rating hợp lệ cho điểm thuộc trip -> 302 chuyển hướng
            r_valid = self.client_a.post(
                f"/trips/{trip_a_id}/rate",
                data={
                    f"score_{valid_dest_id}": "4",
                    f"review_{valid_dest_id}": "Rất đẹp",
                    "csrf_token": tok_a,
                },
            )
            self.assertEqual(r_valid.status_code, 302)

            # Tìm rating vừa tạo và duyệt bởi admin
            pending = self.repo.list_pending_ratings()
            matching = [p for p in pending if p["destination_id"] == valid_dest_id and p["user_id"] == self.user_a_id]
            self.assertEqual(len(matching), 1)
            r_id = matching[0]["id"]
            self.repo.set_rating_approved(r_id, True)
            self.assertTrue(any(d == valid_dest_id for u, d, s in self.repo.list_approved_ratings()))

            # 3. Gửi lại rating mới cho cùng điểm đó -> không nhân đôi dòng và is_approved quay về False
            r_update = self.client_a.post(
                f"/trips/{trip_a_id}/rate",
                data={
                    f"score_{valid_dest_id}": "5",
                    f"review_{valid_dest_id}": "Cập nhật đánh giá",
                    "csrf_token": tok_a,
                },
            )
            self.assertEqual(r_update.status_code, 302)
            # is_approved = False -> không còn trong approved
            self.assertFalse(any(d == valid_dest_id for u, d, s in self.repo.list_approved_ratings()))
            # Chỉ có 1 bản ghi duy nhất trong pending, điểm 5
            pending_after = self.repo.list_pending_ratings()
            matching_after = [p for p in pending_after if p["destination_id"] == valid_dest_id and p["user_id"] == self.user_a_id]
            self.assertEqual(len(matching_after), 1)
            self.assertEqual(matching_after[0]["id"], r_id)
            self.assertEqual(matching_after[0]["score"], 5)

    def test_sharing_generates_new_token_unshare_null_and_leak_prevention(self):
        """Finding #8 & #33: Bật lại chia sẻ cấp token mới, tắt = NULL, trang /s/<token> không lộ email/user_id, có Referrer-Policy."""
        trip_a_id = self._create_trip_for_user_a()
        tok_a = self._get_csrf_token(self.client_a)
        headers_a = {"X-CSRF-Token": tok_a, "Content-Type": "application/json"}

        # Bật chia sẻ lần 1
        r1 = self.client_a.post(f"/api/trips/{trip_a_id}/share", headers=headers_a, json={"is_public": True})
        url1 = r1.get_json()["share_url"]
        token1 = url1.split("/")[-1]

        # Bật chia sẻ lần 2 -> phải ra token mới
        r2 = self.client_a.post(f"/api/trips/{trip_a_id}/share", headers=headers_a, json={"is_public": True})
        url2 = r2.get_json()["share_url"]
        token2 = url2.split("/")[-1]
        self.assertNotEqual(token1, token2)

        # Tắt chia sẻ -> share_url = None, share_token = None
        r_off = self.client_a.post(f"/api/trips/{trip_a_id}/share", headers=headers_a, json={"is_public": False})
        self.assertIsNone(r_off.get_json()["share_url"])
        trip_obj = self.repo.get_trip(trip_a_id)
        self.assertIsNone(trip_obj.share_token)
        self.assertFalse(trip_obj.is_public)

        # Bật lại chia sẻ và kiểm tra trang công khai /s/<token>
        r3 = self.client_a.post(f"/api/trips/{trip_a_id}/share", headers=headers_a, json={"is_public": True})
        token3 = r3.get_json()["share_url"].split("/")[-1]

        r_public = self.anon_client.get(f"/s/{token3}")
        self.assertEqual(r_public.status_code, 200)
        # Header Referrer-Policy
        self.assertEqual(r_public.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        # Không lộ email hoặc user_id của chủ sở hữu
        user_a = self.repo.get_user(self.user_a_id)
        page_html = r_public.get_data(as_text=True)
        self.assertNotIn(user_a["email"], page_html)
        self.assertNotIn(f"user_id: {self.user_a_id}", page_html)

    # -------------------------------------------------------------------------
    # 7. Exhaustive CSRF Tests & Login Session Regeneration (Finding #36)
    # -------------------------------------------------------------------------
    def test_csrf_exhaustive_routes_and_login_session_regeneration(self):
        """Finding #36: Mọi route state-changing từ chối nếu thiếu CSRF, login tái tạo token mới."""
        trip_a_id = self._create_trip_for_user_a()

        # 1. Kiểm tra session CSRF token được tái tạo mới khi đăng nhập
        client = self.app.test_client()
        pre_tok = self._get_csrf_token(client)
        self.assertIsNotNone(pre_tok)
        client.post("/login", data={
            "email": "user_a@example.com",
            "password": "passwordA123",
            "csrf_token": pre_tok,
        })
        with client.session_transaction() as sess:
            post_tok = sess.get("csrf_token")
            self.assertIsNotNone(post_tok)
            self.assertNotEqual(pre_tok, post_tok)

        # 2. Liệt kê từng route thay đổi dữ liệu (POST, PATCH, DELETE), không gửi CSRF token -> 403
        bad_client = self.app.test_client()
        routes_to_test = [
            ("POST", "/register", {"email": "x@ex.com", "password": "123", "full_name": "X"}),
            ("POST", "/login", {"email": "user_a@example.com", "password": "passwordA123"}),
            ("POST", "/logout", {}),
            ("POST", "/trips/new", {"province": "Đà Lạt"}),
            ("POST", f"/trips/{trip_a_id}/delete", {}),
            ("POST", f"/trips/{trip_a_id}/rate", {}),
            ("POST", f"/api/trips/{trip_a_id}/items", {}),
            ("PATCH", f"/api/trips/{trip_a_id}/items/1", {}),
            ("DELETE", f"/api/trips/{trip_a_id}/items/1", {}),
            ("POST", f"/api/trips/{trip_a_id}/share", {}),
            ("POST", f"/api/trips/{trip_a_id}/complete", {}),
        ]

        for method, route, data in routes_to_test:
            if method == "POST":
                res = bad_client.post(route, data=data)
            elif method == "PATCH":
                res = bad_client.patch(route, json=data)
            elif method == "DELETE":
                res = bad_client.delete(route)
            self.assertEqual(res.status_code, 403, f"Route {method} {route} không chặn 403 khi thiếu CSRF!")


if __name__ == "__main__":
    unittest.main()
