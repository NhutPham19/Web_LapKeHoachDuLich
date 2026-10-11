import csv
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


def seed_ratings(csv_path: Path = None, db_url: str = None):
    if csv_path is None:
        csv_path = Path(__file__).parent / "seed" / "ratings.csv"

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
                uid = int(row["user_id"])
                did = int(row["destination_id"])
                score = int(row["score"])
                review = row.get("review_text", "").strip()
                is_approved = row.get("is_approved", "True").lower() in ("true", "1")

                cursor.execute(
                    """
                    SELECT id FROM ratings
                    WHERE user_id = %s AND trip_id IS NULL AND destination_id = %s
                    """,
                    (uid, did),
                )
                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """
                        UPDATE ratings
                        SET score = %s, review_text = %s, is_approved = %s
                        WHERE id = %s
                        """,
                        (score, review, is_approved, existing[0]),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO ratings (user_id, destination_id, score, review_text, is_approved)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (uid, did, score, review, is_approved),
                    )
                count += 1
        conn.commit()
        print(f"Đã nạp thành công {count} ratings từ {csv_path.name}")
        return count
    except Exception as e:
        conn.rollback()
        print(f"Lỗi khi nạp dữ liệu ratings: {e}", file=sys.stderr)
        raise e
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    seed_ratings()
