import csv
import json
from pathlib import Path
import unittest

from app.contracts import INTERESTS, PROVINCES, WEEKDAY_KEYS


SEED_FILE = Path(__file__).parent.parent / "db" / "seed" / "destinations.csv"

# Bounding box tọa độ lãnh thổ Việt Nam
VN_LAT_MIN, VN_LAT_MAX = 8.0, 24.0
VN_LON_MIN, VN_LON_MAX = 102.0, 110.0

REQUIRED_FIELDS = {
    "name",
    "province",
    "address",
    "latitude",
    "longitude",
    "category_name",
    "price_range",
    "noise_level",
    "duration_hours",
    "is_outdoor",
    "opening_hours",
    "tags",
    "description",
    "image_url",
    "image_public_id",
    "image_source",
    "image_author",
    "image_license",
    "image_source_url",
}


class SeedDataIntegrityTests(unittest.TestCase):
    """
    Task T3 (Claude Specification): Kiểm tra tính toàn vẹn của dữ liệu seed CSV offline
    trước khi nạp vào PostgreSQL, chặn đứng dữ liệu rác hoặc sai định dạng.
    """

    def test_seed_destinations_csv_integrity(self):
        self.assertTrue(SEED_FILE.exists(), f"Không tìm thấy file seed: {SEED_FILE}")

        with open(SEED_FILE, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = set(reader.fieldnames or [])
            missing_fields = REQUIRED_FIELDS - fieldnames
            self.assertFalse(
                missing_fields,
                f"File seed thiếu các trường bắt buộc: {missing_fields}",
            )

            seen_pairs = set()
            row_count = 0

            for i, row in enumerate(reader, start=2):
                row_count += 1
                name = row.get("name", "").strip()
                province = row.get("province", "").strip()

                # 1. Tên và Hub không được để trống
                self.assertTrue(name, f"Dòng {i}: name không được để trống")
                self.assertTrue(province, f"Dòng {i}: province không được để trống")
                self.assertIn(
                    province,
                    PROVINCES,
                    f"Dòng {i}: province '{province}' không thuộc PROVINCES ({PROVINCES})",
                )

                # 2. Không được trùng tên trong cùng một Hub
                pair = (province, name)
                self.assertNotIn(
                    pair,
                    seen_pairs,
                    f"Dòng {i}: trùng lặp địa điểm '{name}' tại hub '{province}'",
                )
                seen_pairs.add(pair)

                # 3. Tọa độ GPS nằm trong Bounding Box Việt Nam
                try:
                    lat = float(row["latitude"])
                    lon = float(row["longitude"])
                except ValueError:
                    self.fail(f"Dòng {i}: tọa độ latitude/longitude không phải số thực")

                self.assertTrue(
                    VN_LAT_MIN <= lat <= VN_LAT_MAX,
                    f"Dòng {i}: latitude {lat} nằm ngoài lãnh thổ Việt Nam ({VN_LAT_MIN} - {VN_LAT_MAX})",
                )
                self.assertTrue(
                    VN_LON_MIN <= lon <= VN_LON_MAX,
                    f"Dòng {i}: longitude {lon} nằm ngoài lãnh thổ Việt Nam ({VN_LON_MIN} - {VN_LON_MAX})",
                )

                # 4. price_range và noise_level
                price_range = int(row["price_range"])
                self.assertTrue(
                    1 <= price_range <= 4,
                    f"Dòng {i}: price_range={price_range} phải nằm trong khoảng 1..4",
                )
                noise_level = int(row["noise_level"])
                self.assertTrue(
                    1 <= noise_level <= 5,
                    f"Dòng {i}: noise_level={noise_level} phải nằm trong khoảng 1..5",
                )

                # 5. duration_hours
                duration = float(row["duration_hours"])
                self.assertTrue(
                    0.5 <= duration <= 6.0,
                    f"Dòng {i}: duration_hours={duration} phải hợp lý (0.5..6.0h)",
                )

                # 6. is_outdoor
                is_outdoor_str = row.get("is_outdoor", "").strip().lower()
                self.assertIn(
                    is_outdoor_str,
                    ("true", "false", "1", "0"),
                    f"Dòng {i}: is_outdoor phải là boolean (True/False)",
                )

                # 7. opening_hours parse được JSON nếu có
                opening_raw = row.get("opening_hours", "").strip()
                if opening_raw:
                    try:
                        opening = json.loads(opening_raw)
                        self.assertIsInstance(opening, dict)
                        self.assertTrue(
                            set(opening.keys()).issubset(set(WEEKDAY_KEYS)),
                            f"Dòng {i}: opening_hours có thứ không hợp lệ",
                        )
                    except Exception as e:
                        self.fail(f"Dòng {i}: opening_hours JSON không hợp lệ: {e}")

                # 8. tags parse được JSON và thuộc INTERESTS taxonomy
                tags_raw = row.get("tags", "").strip()
                self.assertTrue(tags_raw, f"Dòng {i}: tags không được để trống")
                try:
                    tags = json.loads(tags_raw)
                    self.assertIsInstance(tags, list)
                    self.assertTrue(
                        set(tags).issubset(set(INTERESTS)),
                        f"Dòng {i}: tags {tags} chứa thẻ ngoài taxonomy INTERESTS",
                    )
                except Exception as e:
                    self.fail(f"Dòng {i}: tags JSON không hợp lệ: {e}")

                # 9. image metadata (Claude Task T2 & T5)
                img_source = row.get("image_source", "").strip()
                self.assertIn(img_source, ("wikimedia", "placeholder"), f"Dòng {i}: image_source không hợp lệ: {img_source}")
                pub_id = row.get("image_public_id", "").strip()
                self.assertTrue(pub_id.startswith("dulich_vn/destinations/"), f"Dòng {i}: image_public_id sai định dạng: {pub_id}")
                if img_source == "wikimedia":
                    self.assertTrue(row.get("image_author", "").strip(), f"Dòng {i}: ảnh wikimedia thiếu image_author")
                    self.assertTrue(row.get("image_license", "").strip(), f"Dòng {i}: ảnh wikimedia thiếu image_license")

            self.assertGreater(row_count, 0, "File seed destinations.csv không có dòng dữ liệu nào")

    def test_seed_each_hub_satisfies_claude_constraints(self):
        """
        Kiểm tra các ràng buộc chất lượng nghiêm ngặt của Claude cho từng Hub (1A):
        - Mỗi hub có >= 15 địa điểm.
        - Mỗi hub có >= 3 điểm ẩm thực.
        - Mỗi hub có >= 4 điểm trong nhà (is_outdoor=False).
        - Mỗi hub có >= 2 điểm miễn phí vé (ticket_price=0 hoặc price_range=1).
        """
        with open(SEED_FILE, mode="r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        hubs = set(row["province"] for row in reader)
        self.assertEqual(hubs, set(PROVINCES))

        for hub in hubs:
            hub_rows = [r for r in reader if r["province"] == hub]
            self.assertGreaterEqual(
                len(hub_rows), 15,
                f"Hub '{hub}' có ít hơn 15 địa điểm (hiện có: {len(hub_rows)})"
            )

            food_count = sum(
                1 for r in hub_rows
                if r.get("category_name") == "Am thuc" or "am_thuc" in json.loads(r.get("tags", "[]"))
            )
            self.assertGreaterEqual(
                food_count, 3,
                f"Hub '{hub}' có ít hơn 3 điểm ẩm thực (hiện có: {food_count})"
            )

            indoor_count = sum(
                1 for r in hub_rows
                if r.get("is_outdoor", "").strip().lower() in ("false", "0")
            )
            self.assertGreaterEqual(
                indoor_count, 4,
                f"Hub '{hub}' có ít hơn 4 điểm trong nhà (hiện có: {indoor_count})"
            )

            free_count = sum(
                1 for r in hub_rows
                if int(r.get("ticket_price", 0)) == 0 or int(r.get("price_range", 1)) == 1
            )
            self.assertGreaterEqual(
                free_count, 2,
                f"Hub '{hub}' có ít hơn 2 điểm miễn phí vé (hiện có: {free_count})"
            )

    def test_seed_ratings_csv_integrity(self):
        """
        Claude Task T6: Kiểm tra tính toàn vẹn của dữ liệu seed ratings.csv:
        - 600 - 1.000 ratings mô phỏng.
        - 40 - 60 users mẫu, mỗi user >= 5 ratings.
        - Điểm score trong [1, 5], is_approved là True.
        - Không có trùng lặp (user_id, destination_id).
        """
        ratings_file = Path(__file__).parent.parent / "db" / "seed" / "ratings.csv"
        self.assertTrue(ratings_file.exists(), f"Không tìm thấy file seed ratings: {ratings_file}")

        with open(ratings_file, mode="r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        self.assertGreaterEqual(len(reader), 600, "Tổng số ratings phải >= 600")
        self.assertLessEqual(len(reader), 1000, "Tổng số ratings phải <= 1000")

        users = set()
        user_counts = {}
        seen_pairs = set()

        for idx, row in enumerate(reader, start=2):
            uid = int(row["user_id"])
            did = int(row["destination_id"])
            score = int(row["score"])
            is_approved = row["is_approved"].strip().lower() in ("true", "1")

            self.assertIn(score, range(1, 6), f"Dòng {idx}: score {score} không nằm trong [1, 5]")
            self.assertTrue(is_approved, f"Dòng {idx}: is_approved phải là True")
            self.assertTrue(1 <= did <= 96, f"Dòng {idx}: destination_id {did} ngoài phạm vi 1..96")

            pair = (uid, did)
            self.assertNotIn(pair, seen_pairs, f"Dòng {idx}: Trùng cặp (user_id={uid}, destination_id={did})")
            seen_pairs.add(pair)

            users.add(uid)
            user_counts[uid] = user_counts.get(uid, 0) + 1

        self.assertTrue(40 <= len(users) <= 60, f"Số users ({len(users)}) phải nằm trong [40, 60]")
        for uid, count in user_counts.items():
            self.assertGreaterEqual(count, 5, f"User {uid} có ít hơn 5 ratings ({count})")

    def test_image_manifest_csv_integrity(self):
        """Claude Task T5: Kiểm tra tính toàn vẹn của image_manifest.csv (96 địa điểm, có attribution)."""
        manifest_file = Path(__file__).parent.parent / "db" / "seed" / "image_manifest.csv"
        self.assertTrue(manifest_file.exists(), f"Không tìm thấy manifest file: {manifest_file}")
        with open(manifest_file, mode="r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 96, "Image manifest phải chứa đúng 96 địa điểm")
        for idx, row in enumerate(reader, start=2):
            self.assertIn(row["review_status"], ("APPROVED", "PLACEHOLDER"))
            self.assertTrue(row["image_public_id"].startswith("dulich_vn/destinations/"))
            if row["review_status"] == "APPROVED":
                self.assertTrue(row["thumbnail_url"].startswith("http"))
                self.assertTrue(row["image_license"])


if __name__ == "__main__":
    unittest.main()
