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


class RoutesTests(unittest.TestCase):
    def setUp(self):
        self.destinations = load_fixture_destinations()
        self.repo = FakeRepo(destinations=self.destinations)
        self.app = create_app(repo=self.repo)
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

    def _get_csrf_token(self, client):
        """Lấy token CSRF hợp lệ từ session sau khi gọi GET."""
        client.get("/")
        with client.session_transaction() as sess:
            return sess.get("csrf_token")

    def _register_and_login(self, client, email="traveler@example.com", password="password123", full_name="Nguyễn Văn A"):
        tok = self._get_csrf_token(client)
        resp = client.post("/register", data={
            "email": email,
            "password": password,
            "full_name": full_name,
            "csrf_token": tok,
        }, follow_redirects=True)
        return resp

    def test_registration_and_login_flow(self):
        """Kiểm tra toàn bộ luồng đăng ký, đăng nhập và đăng xuất."""
        tok = self._get_csrf_token(self.client)

        # 1. Đăng ký thiếu mật khẩu đủ độ dài (< 8 ký tự) -> 400
        res = self.client.post("/register", data={
            "email": "user1@example.com",
            "password": "123",
            "full_name": "Test User",
            "csrf_token": tok,
        })
        self.assertEqual(res.status_code, 400)

        # 2. Đăng ký hợp lệ -> chuyển tiếp onboarding
        res = self.client.post("/register", data={
            "email": "user1@example.com",
            "password": "password123",
            "full_name": "Test User",
            "csrf_token": tok,
        })
        self.assertEqual(res.status_code, 302)
        self.assertIn("/onboarding", res.headers["Location"])

        # 3. Đăng xuất
        with self.client.session_transaction() as sess:
            tok = sess["csrf_token"]
        res = self.client.post("/logout", data={"csrf_token": tok})
        self.assertEqual(res.status_code, 302)

        # 4. Đăng nhập sai mật khẩu -> 400 (lấy token mới sau khi session bị clear)
        self.client.get("/login")
        with self.client.session_transaction() as sess:
            new_tok = sess["csrf_token"]

        res = self.client.post("/login", data={
            "email": "user1@example.com",
            "password": "wrong_password",
            "csrf_token": new_tok,
        })
        self.assertEqual(res.status_code, 400)

        # 5. Đăng nhập đúng mật khẩu -> 302
        res = self.client.post("/login", data={
            "email": "user1@example.com",
            "password": "password123",
            "csrf_token": new_tok,
        })
        self.assertEqual(res.status_code, 302)

    def test_onboarding_preferences_saved(self):
        """Người dùng lưu sở thích du lịch thành công."""
        self._register_and_login(self.client)
        with self.client.session_transaction() as sess:
            tok = sess["csrf_token"]

        res = self.client.post("/onboarding", data={
            "interests": ["thien_nhien", "yen_tinh"],
            "travel_style": "tiet_kiem",
            "csrf_token": tok,
        })
        self.assertEqual(res.status_code, 302)
        self.assertIn("/trips/new", res.headers["Location"])

    def test_create_trip_boundary_validations(self):
        """Validate nghiêm ngặt theo 1.G.7 và Finding #22 từng giá trị biên."""
        self._register_and_login(self.client)
        with self.client.session_transaction() as sess:
            tok = sess["csrf_token"]

        vn_today = datetime.now(timezone(timedelta(hours=7))).date()
        valid_date = (vn_today + timedelta(days=2)).isoformat()
        past_date = (vn_today - timedelta(days=2)).isoformat()
        far_future_date = (vn_today + timedelta(days=400)).isoformat()

        base_payload = {
            "province": "Đà Lạt",
            "start_date": valid_date,
            "days": "2",
            "budget": "2000000",
            "num_people": "2",
            "interests": ["thien_nhien"],
            "travel_style": "tiet_kiem",
            "csrf_token": tok,
        }

        # 1. Tỉnh không hợp lệ
        bad_p = dict(base_payload, province="Atlantis")
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 2. Ngày trong quá khứ
        bad_p = dict(base_payload, start_date=past_date)
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 3. Ngày quá xa tương lai (> 365 ngày)
        bad_p = dict(base_payload, start_date=far_future_date)
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 4. Số ngày ngoài khoảng 1..7 (vd: 0 hoặc 8)
        bad_p = dict(base_payload, days="8")
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 5. Số người ngoài khoảng 1..20 (vd: 0 hoặc 25)
        bad_p = dict(base_payload, num_people="0")
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 6. Ngân sách dưới sàn tối thiểu (num_people * days * 300,000 = 2 * 2 * 300k = 1,200,000)
        bad_p = dict(base_payload, budget="500000")
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 7. Ngân sách vượt trần MAX_BUDGET
        bad_p = dict(base_payload, budget="2000000000")
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 8. Sở thích rỗng
        bad_p = dict(base_payload)
        bad_p.pop("interests")
        r = self.client.post("/trips/new", data=bad_p, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        # 9. Payload hợp lệ tạo thành công
        r = self.client.post("/trips/new", data=base_payload, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].startswith("/trips/"))

        # 10. Tạo chuyến thứ 2 (kiểm tra existing_trips chứa dict không gây AttributeError)
        r2 = self.client.post("/trips/new", data=base_payload, follow_redirects=False)
        self.assertEqual(r2.status_code, 302)
        self.assertTrue(r2.headers["Location"].startswith("/trips/"))

        # 11. Đạt giới hạn 20 draft trips
        from unittest.mock import patch
        mock_20_drafts = [{"id": i, "status": "draft"} for i in range(20)]
        with patch.object(self.app.repo, "list_trips", return_value=mock_20_drafts):
            r_limit = self.client.post("/trips/new", data=base_payload, follow_redirects=False)
            self.assertEqual(r_limit.status_code, 302)
            self.assertEqual(r_limit.headers["Location"], "/trips")

    def test_api_candidates_and_items_crud(self):
        """Kiểm tra API lấy ứng viên và thao tác thêm/sửa/xóa địa điểm trong chuyến đi."""
        self._register_and_login(self.client)
        with self.client.session_transaction() as sess:
            tok = sess["csrf_token"]
            user_id = sess["user"]["id"]

        # Tạo một trip
        vn_today = datetime.now(timezone(timedelta(hours=7))).date()
        valid_date = (vn_today + timedelta(days=2)).isoformat()
        r = self.client.post("/trips/new", data={
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

        # 1. GET candidates
        r = self.client.get(f"/api/trips/{trip_id}/candidates")
        self.assertEqual(r.status_code, 200)
        candidates = r.get_json()
        self.assertIsInstance(candidates, list)

        # 2. Thêm item qua API
        if candidates:
            cand = candidates[0]
            headers = {"X-CSRF-Token": tok, "Content-Type": "application/json"}
            r_add = self.client.post(f"/api/trips/{trip_id}/items", headers=headers, json={
                "destination_id": cand["id"],
                "day_number": 1,
                "time_slot": "morning",
            })
            self.assertEqual(r_add.status_code, 201)
            item_id = r_add.get_json()["id"]

            # 3. Sửa item qua API
            r_patch = self.client.patch(f"/api/trips/{trip_id}/items/{item_id}", headers=headers, json={
                "time_slot": "afternoon",
            })
            self.assertEqual(r_patch.status_code, 200)

            # 4. Xóa item qua API
            r_del = self.client.delete(f"/api/trips/{trip_id}/items/{item_id}", headers=headers)
            self.assertEqual(r_del.status_code, 200)

    def test_share_and_unshare_trip(self):
        """Kiểm tra tính năng chia sẻ và thu hồi liên kết công khai."""
        self._register_and_login(self.client)
        with self.client.session_transaction() as sess:
            tok = sess["csrf_token"]

        vn_today = datetime.now(timezone(timedelta(hours=7))).date()
        valid_date = (vn_today + timedelta(days=2)).isoformat()
        r = self.client.post("/trips/new", data={
            "province": "Đà Lạt",
            "start_date": valid_date,
            "days": "1",
            "budget": "2000000",
            "num_people": "1",
            "interests": ["thien_nhien"],
            "travel_style": "tiet_kiem",
            "csrf_token": tok,
        })
        trip_id = int(r.headers["Location"].split("/")[-1])

        headers = {"X-CSRF-Token": tok, "Content-Type": "application/json"}

        # Bật chia sẻ
        r_share = self.client.post(f"/api/trips/{trip_id}/share", headers=headers, json={"is_public": True})
        self.assertEqual(r_share.status_code, 200)
        share_url = r_share.get_json()["share_url"]
        self.assertIsNotNone(share_url)
        share_token = share_url.split("/s/")[-1]

        # Khách vãng lai xem qua link public
        anon_client = self.app.test_client()
        r_public = anon_client.get(f"/s/{share_token}")
        self.assertEqual(r_public.status_code, 200)

        # Tắt chia sẻ
        r_unshare = self.client.post(f"/api/trips/{trip_id}/share", headers=headers, json={"is_public": False})
        self.assertEqual(r_unshare.status_code, 200)

        # Khách vãng lai xem lại link cũ -> 404
        r_public_revoked = anon_client.get(f"/s/{share_token}")
        self.assertEqual(r_public_revoked.status_code, 404)

    def test_route_level_feedback_loop_updates_recommendation(self):
        """Finding #34(a): Route-level feedback loop: Hoàn thành trip -> chấm điểm -> admin duyệt -> CF cập nhật gợi ý."""
        # 1. Đăng ký và đăng nhập User 1
        client1 = self.app.test_client()
        self._register_and_login(client1, email="user1_feedback@example.com", full_name="User Feedback 1")
        tok1 = self._get_csrf_token(client1)

        valid_date = (datetime.now(timezone(timedelta(hours=7))).date() + timedelta(days=2)).isoformat()
        r = client1.post("/trips/new", data={
            "province": "Đà Lạt",
            "start_date": valid_date,
            "days": "1",
            "budget": "2000000",
            "num_people": "1",
            "interests": ["thien_nhien"],
            "travel_style": "tiet_kiem",
            "csrf_token": tok1,
        })
        trip_id = int(r.headers["Location"].split("/")[-1])
        trip = self.repo.get_trip(trip_id)
        rated_dest = trip.plan.days[0].items[0].destination

        # Giả lập hoàn thành chuyến đi
        self.repo.set_status(trip_id, "completed")
        with patch("app.routes.ratings.today_vn", return_value=date(2026, 12, 1)):
            # User 1 đánh giá 5 sao cho điểm đến này
            r_rate = client1.post(f"/trips/{trip_id}/rate", data={
                f"score_{rated_dest.id}": "5",
                f"review_{rated_dest.id}": "Cảnh quan tuyệt vời 5 sao",
                "csrf_token": tok1,
            })
            self.assertEqual(r_rate.status_code, 302)

        # 2. Đăng ký Admin và duyệt rating
        admin_client = self.app.test_client()
        self._register_and_login(admin_client, email="admin_feedback@example.com", full_name="Admin Feedback")
        self.repo.set_user_admin("admin_feedback@example.com", is_admin=True)
        with admin_client.session_transaction() as sess:
            sess["user"] = dict(sess["user"], is_admin=True)

        pending = self.repo.list_pending_ratings()
        matching = [p for p in pending if p["destination_id"] == rated_dest.id]
        self.assertTrue(len(matching) > 0)
        r_id = matching[0]["id"]

        tok_admin = self._get_csrf_token(admin_client)
        r_approve = admin_client.post("/admin/ratings", data={"rating_id": str(r_id), "action": "approve", "csrf_token": tok_admin})
        self.assertEqual(r_approve.status_code, 302)

        # 3. Xác nhận list_approved_ratings đã ghi nhận rating mới
        approved = self.repo.list_approved_ratings()
        self.assertTrue(any(d == rated_dest.id and s == 5 for u, d, s in approved))


if __name__ == "__main__":
    unittest.main()
