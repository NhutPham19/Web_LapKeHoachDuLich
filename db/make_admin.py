import os
import sys

# Thêm thư mục gốc vào sys.path để import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import PgRepo

def main():
    if len(sys.argv) < 2:
        print("Cách dùng: python db/make_admin.py <email>")
        sys.exit(1)

    email = sys.argv[1].strip()
    repo = PgRepo()
    user = repo.get_user_by_email(email)
    if not user:
        print(f"Lỗi: Không tìm thấy người dùng có email: {email}")
        sys.exit(1)

    ok = repo.set_user_admin(email, is_admin=True)
    if ok:
        print(f"Thành công: Đã cấp quyền Quản trị viên (Admin) cho {email}")
    else:
        print(f"Lỗi: Không thể cập nhật quyền cho {email}")
        sys.exit(1)

if __name__ == "__main__":
    main()
