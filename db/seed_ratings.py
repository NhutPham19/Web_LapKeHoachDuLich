import os
import random
import sys
import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()


def get_db_connection(db_url: str = None):
    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL không được để trống")
    return psycopg2.connect(url)


def seed_ratings(num_users: int = 15, ratings_per_user: int = 5, db_url: str = None):
    """
    Sinh người dùng giả lập (synthetic_<n>@example.com) và ratings giả lập
    với seed cố định để đảm bảo kết quả tái lập được.
    """
    random.seed(42)
    conn = get_db_connection(db_url)
    cursor = conn.cursor()

    try:
        # Lấy danh sách destination id
        cursor.execute("SELECT id FROM destinations")
        dest_rows = cursor.fetchall()
        if not dest_rows:
            print("Chưa có địa điểm nào trong CSDL để tạo ratings.")
            return 0
        dest_ids = [r[0] for r in dest_rows]

        # 1. Tạo các user giả lập
        user_ids = []
        default_pwd_hash = generate_password_hash("synthetic_pass_123")
        for i in range(1, num_users + 1):
            email = f"synthetic_{i}@example.com"
            full_name = f"Người dùng giả lập {i}"
            cursor.execute(
                """
                INSERT INTO users (email, password_hash, full_name, is_admin)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (email) DO UPDATE SET full_name = EXCLUDED.full_name
                RETURNING id
                """,
                (email, default_pwd_hash, full_name),
            )
            user_id = cursor.fetchone()[0]
            user_ids.append(user_id)

        # 2. Tạo ratings giả lập có cấu trúc
        # Nhóm chẵn: thích các điểm đầu (score 4-5)
        # Nhóm lẻ: thích các điểm cuối (score 4-5)
        rating_count = 0
        for idx, u_id in enumerate(user_ids):
            # Chọn các điểm đánh giá
            chosen_dests = random.sample(dest_ids, min(len(dest_ids), ratings_per_user))
            for d_id in chosen_dests:
                if idx % 2 == 0:
                    score = random.choice([4, 5]) if d_id % 2 == 0 else random.choice([1, 2, 3])
                else:
                    score = random.choice([4, 5]) if d_id % 2 != 0 else random.choice([1, 2, 3])

                cursor.execute(
                    """
                    SELECT id FROM ratings
                    WHERE user_id = %s AND destination_id = %s
                    """,
                    (u_id, d_id),
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        """
                        UPDATE ratings
                        SET score = %s, review_text = %s, is_approved = TRUE
                        WHERE id = %s
                        """,
                        (score, f"Đánh giá giả lập từ synthetic user {u_id}", existing[0]),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO ratings (user_id, destination_id, score, review_text, is_approved)
                        VALUES (%s, %s, %s, %s, TRUE)
                        """,
                        (u_id, d_id, score, f"Đánh giá giả lập từ synthetic user {u_id}"),
                    )
                rating_count += 1

        # 3. Cập nhật avg_rating cho các destinations
        cursor.execute(
            """
            UPDATE destinations d
            SET avg_rating = sub.avg_score
            FROM (
                SELECT destination_id, ROUND(AVG(score)::numeric, 1) as avg_score
                FROM ratings
                WHERE is_approved = TRUE
                GROUP BY destination_id
            ) sub
            WHERE d.id = sub.destination_id
            """
        )

        conn.commit()
        print(f"Đã nạp thành công {len(user_ids)} users và {rating_count} ratings giả lập.")
        return rating_count
    except Exception as e:
        conn.rollback()
        print(f"Lỗi khi tạo ratings giả lập: {e}", file=sys.stderr)
        raise e
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    seed_ratings()
