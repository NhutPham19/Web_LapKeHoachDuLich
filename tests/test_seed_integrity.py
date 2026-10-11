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

            self.assertGreater(row_count, 0, "File seed destinations.csv không có dòng dữ liệu nào")


if __name__ == "__main__":
    unittest.main()
