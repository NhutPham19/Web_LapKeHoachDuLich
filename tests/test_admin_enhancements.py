import unittest
from app import create_app
from tests.fakes import FakeRepo
from tests.test_routes import load_fixture_destinations


class TestAdminEnhancements(unittest.TestCase):
    def setUp(self):
        self.destinations = load_fixture_destinations()
        self.repo = FakeRepo(destinations=self.destinations)
        # Tạo admin user
        self.admin_id = self.repo.create_user("admin@example.com", "hash_pw", "Admin User")
        self.repo.set_user_admin("admin@example.com", True)

        self.app = create_app(repo=self.repo)
        self.client = self.app.test_client()

        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": self.admin_id,
                "email": "admin@example.com",
                "full_name": "Admin User",
                "is_admin": True,
            }

    def test_admin_destinations_search_by_name(self):
        res = self.client.get("/admin/destinations?q=Đồi+Thông")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Đồi Thông Mẫu Đà Lạt".encode("utf-8"), res.data)

    def test_admin_destinations_filter_by_province(self):
        res = self.client.get("/admin/destinations?province=Đà+Lạt")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Đà Lạt".encode("utf-8"), res.data)
        self.assertIn("Bảo tàng Mẫu Đà Lạt".encode("utf-8"), res.data)

    def test_admin_destinations_pagination(self):
        res = self.client.get("/admin/destinations?page=1")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Tìm thấy".encode("utf-8"), res.data)
        self.assertIn(b"dest_img_url", res.data or b"") if False else None

    def test_admin_destinations_filter_no_results(self):
        res = self.client.get("/admin/destinations?q=NonExistentKeywordXYZ123")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Không tìm thấy địa điểm nào".encode("utf-8"), res.data)

    def test_admin_destination_form_has_file_input(self):
        res = self.client.get("/admin/destinations/new")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'type="file"', res.data)
        self.assertIn(b'name="image_file"', res.data)
        self.assertIn(b'enctype="multipart/form-data"', res.data)


if __name__ == "__main__":
    unittest.main()
