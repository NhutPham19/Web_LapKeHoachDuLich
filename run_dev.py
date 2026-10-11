import json
import os
from pathlib import Path
from werkzeug.security import generate_password_hash

from app import create_app
from app.contracts import Destination
from tests.fakes import FakeRepo
from tests.fixtures.ratings import SYNTHETIC_RATINGS

import csv


def load_demo_repo():
    seed_csv = Path(__file__).parent / "db" / "seed" / "destinations.csv"
    fixture_path = Path(__file__).parent / "tests" / "fixtures" / "destinations.json"
    destinations = []

    if seed_csv.exists():
        cat_map = {"Thien nhien": 1, "Van hoa": 2, "Di tich": 2, "Am thuc": 3, "Vui choi": 4}
        with open(seed_csv, "r", encoding="utf-8") as f:
            for idx, row in enumerate(csv.DictReader(f), start=1):
                raw_hours = row.get("opening_hours", "")
                hours = json.loads(raw_hours) if raw_hours else None
                raw_tags = row.get("tags", "")
                tags = tuple(json.loads(raw_tags)) if raw_tags else ()
                destinations.append(
                    Destination(
                        id=idx,
                        name=row["name"].strip(),
                        province=row["province"].strip(),
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        category_id=cat_map.get(row.get("category_name", "").strip(), 1),
                        price_range=int(row["price_range"]),
                        noise_level=int(row["noise_level"]),
                        duration_hours=float(row["duration_hours"]),
                        is_outdoor=row["is_outdoor"].strip().lower() in ("true", "1"),
                        ticket_price=int(row.get("ticket_price", 0)),
                        opening_hours=hours,
                        tags=tags,
                        description=row.get("description", "").strip(),
                        image_url=row.get("image_url", "").strip(),
                        image_public_id=row.get("image_public_id") or None,
                        image_source=row.get("image_source", "placeholder").strip(),
                        image_author=row.get("image_author", "").strip(),
                        image_license=row.get("image_license", "").strip(),
                        image_source_url=row.get("image_source_url", "").strip(),
                    )
                )
    elif fixture_path.exists():
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("destinations", []):
                vals = dict(item)
                vals["tags"] = tuple(vals.get("tags", []))
                destinations.append(Destination(**vals))

    repo = FakeRepo(destinations)

    # Nạp danh mục mẫu
    repo.save_category("Thiên nhiên & Sinh thái", "bi-tree")
    repo.save_category("Văn hóa & Di sản", "bi-bank")
    repo.save_category("Ẩm thực & Mua sắm", "bi-cup-hot")
    repo.save_category("Biển đảo & Nghỉ dưỡng", "bi-water")

    # Tạo 2 tài khoản mẫu để test
    # 1. Admin: admin@example.com / admin123456
    admin_id = repo.create_user("admin@example.com", generate_password_hash("admin123456"), "Quản Trị Viên")
    repo.set_user_admin("admin@example.com", is_admin=True)
    repo.save_preferences(admin_id, ["thien_nhien", "van_hoa"], "thoai_mai")

    # 2. Người dùng: user@example.com / user123456
    user_id = repo.create_user("user@example.com", generate_password_hash("user123456"), "Nguyễn Văn Demo")
    repo.save_preferences(user_id, ["thien_nhien", "yen_tinh", "am_thuc"], "tiet_kiem")

    # Nạp ratings mẫu để thuật toán Collaborative Filtering có dữ liệu chạy ngay
    ratings_csv = Path(__file__).parent / "db" / "seed" / "ratings.csv"
    if ratings_csv.exists():
        with open(ratings_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                r_id = repo.save_rating(
                    int(row["user_id"]),
                    int(row["destination_id"]),
                    1,
                    int(row["score"]),
                    row.get("review_text", ""),
                )
                repo.set_rating_approved(r_id, True)
    else:
        for uid, did, score in SYNTHETIC_RATINGS:
            r_id = repo.save_rating(uid, did, 1, score, "Đánh giá giả lập trải nghiệm")
            repo.set_rating_approved(r_id, True)

    return repo


if __name__ == "__main__":
    os.environ.setdefault("SECRET_KEY", "dev-secret-key-dulich-2026")
    
    # Ưu tiên kết nối PostgreSQL thật nếu có cấu hình, nếu không tự động dùng InMemory FakeRepo
    repo = None
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        try:
            from app.db import PgRepo
            pg = PgRepo(db_url)
            if pg.ping_db():
                repo = pg
                print(">>> Đang sử dụng cơ sở dữ liệu PostgreSQL:", db_url)
        except Exception:
            pass

    if repo is None:
        print(">>> Khởi động ở chế độ Demo (Bộ nhớ InMemory) với dữ liệu mẫu hoàn chỉnh!")
        repo = load_demo_repo()

    app = create_app(repo=repo)
    print("\n" + "=" * 60)
    print(" WEBSITE LẬP KẾ HOẠCH DU LỊCH ĐÃ SẴN SÀNG!")
    print(" Truy cập trình duyệt: http://127.0.0.1:5000")
    print("-" * 60)
    print(" TÀI KHOẢN MẪU ĐỂ TEST NGAY:")
    print("   1. User thường : user@example.com  | Mật khẩu: user123456")
    print("   2. Quản trị viên: admin@example.com | Mật khẩu: admin123456")
    print("=" * 60 + "\n")
    
    app.run(host="127.0.0.1", port=5000, debug=True)
