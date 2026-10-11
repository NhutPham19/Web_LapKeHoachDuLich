import csv
import json
import os
import sys
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_db_connection(db_url: str = None):
    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL không được để trống")
    return psycopg2.connect(url)


def seed_destinations(csv_path: Path = None, db_url: str = None):
    if csv_path is None:
        csv_path = Path(__file__).parent / "seed" / "destinations.csv"

    if not csv_path.exists():
        print(f"File CSV không tồn tại: {csv_path}")
        return 0

    conn = get_db_connection(db_url)
    cursor = conn.cursor()

    count = 0
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cat_name = row.get("category_name", "").strip() or "Khác"
                cursor.execute(
                    """
                    INSERT INTO categories (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (cat_name,),
                )
                category_id = cursor.fetchone()[0]

                opening_raw = row.get("opening_hours", "").strip()
                opening_json = json.loads(opening_raw) if opening_raw else None

                tags_raw = row.get("tags", "").strip()
                tags_json = json.loads(tags_raw) if tags_raw else []

                cursor.execute(
                    """
                    SELECT id FROM destinations
                    WHERE name = %s AND province = %s
                    """,
                    (row["name"].strip(), row["province"].strip()),
                )
                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """
                        UPDATE destinations
                        SET address = %s, latitude = %s, longitude = %s,
                            description = %s, image_url = %s, category_id = %s,
                            price_range = %s, noise_level = %s, duration_hours = %s,
                            is_outdoor = %s, opening_hours = %s, tags = %s
                        WHERE id = %s
                        """,
                        (
                            row.get("address", "").strip(),
                            float(row["latitude"]),
                            float(row["longitude"]),
                            row.get("description", "").strip(),
                            row.get("image_url", "").strip(),
                            category_id,
                            int(row["price_range"]),
                            int(row["noise_level"]),
                            float(row["duration_hours"]),
                            row.get("is_outdoor", "True").lower() in ("true", "1"),
                            json.dumps(opening_json) if opening_json else None,
                            json.dumps(tags_json),
                            existing[0],
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO destinations (
                            name, province, address, latitude, longitude,
                            description, image_url, category_id,
                            price_range, noise_level, duration_hours,
                            is_outdoor, opening_hours, tags
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s
                        )
                        """,
                        (
                            row["name"].strip(),
                            row["province"].strip(),
                            row.get("address", "").strip(),
                            float(row["latitude"]),
                            float(row["longitude"]),
                            row.get("description", "").strip(),
                            row.get("image_url", "").strip(),
                            category_id,
                            int(row["price_range"]),
                            int(row["noise_level"]),
                            float(row["duration_hours"]),
                            row.get("is_outdoor", "True").lower() in ("true", "1"),
                            json.dumps(opening_json) if opening_json else None,
                            json.dumps(tags_json),
                        ),
                    )
                count += 1
        conn.commit()
        print(f"Đã nạp thành công {count} địa điểm từ {csv_path.name}")
        return count
    except Exception as e:
        conn.rollback()
        print(f"Lỗi khi nạp dữ liệu: {e}", file=sys.stderr)
        raise e
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    seed_destinations()
