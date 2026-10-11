# SourceCode_DuLich — Mã Nguồn Website Lập Kế Hoạch Du Lịch Cá Nhân Hóa

> **Lưu ý cho các Agents (ANTIGRAVITY, CODEX, CURSOR):**
> Đây là thư mục gốc chứa toàn bộ mã nguồn của dự án (Git repository chính). Mọi lệnh terminal (chạy test, cài đặt, chạy server) đều phải được thực thi trong thư mục này.

---

## 1. Cấu Trúc Cây Thư Mục

```
SourceCode_DuLich/
├─ app/
│  ├─ __init__.py              # create_app(repo=None), đăng ký blueprints & route /health
│  ├─ contracts.py             # FROZEN — Các hằng số và Dataclass chuẩn hệ thống
│  ├─ config.py                # Đọc cấu hình từ biến môi trường (.env)
│  ├─ auth.py                  # Decorator kiểm tra quyền: login_required, admin_required
│  ├─ db.py                    # Cài đặt PgRepo (PostgreSQL thuần qua psycopg2)
│  ├─ routes/                  # (ANTIGRAVITY): auth.py, trips.py, ratings.py, admin.py
│  ├─ services/                # (ANTIGRAVITY): Các service tính toán thuần
│  │  ├─ content_based.py      # Thuật toán Content-Based (Cosine similarity 11 chiều)
│  │  ├─ collaborative.py      # Thuật toán Collaborative (KNN user-based)
│  │  ├─ recommender.py        # Hybrid Recommender kết hợp CB và CF
│  │  ├─ weather.py            # Xử lý & cache thời tiết OpenWeatherMap
│  │  ├─ itinerary.py          # Greedy itinerary planning & haversine
│  │  ├─ budget.py             # Phân bổ ngân sách & chi phí
│  │  └─ planner.py            # Điều phối toàn bộ kế hoạch chuyến đi
│  ├─ templates/               # (CURSOR): Giao diện Jinja2 + Bootstrap 5
│  └─ static/                  # (CURSOR): File tĩnh frontend
│     ├─ css/                  # Custom CSS (nếu cần)
│     └─ js/                   # Custom JavaScript (gọi API / Leaflet)
├─ db/
│  ├─ schema.sql               # Định nghĩa CSDL PostgreSQL (idempotent DDL)
│  ├─ seed/                    # Chứa destinations.csv và dữ liệu mầm
│  ├─ seed_destinations.py     # Script nạp địa điểm từ CSV vào DB
│  └─ seed_ratings.py          # Script sinh đánh giá giả lập (synthetic)
├─ tests/                      # (CODEX): Toàn bộ mã kiểm thử và mock
│  ├─ fakes.py                 # FakeRepo triển khai InMemory cho Repository
│  ├─ fixtures/                # Dữ liệu mẫu JSON: destinations, ratings, weather, plan
│  └─ test_*.py                # Các test case unittest độc lập
├─ .github/
│  └─ workflows/
│     └─ keepalive.yml         # GitHub Actions định kỳ ping /health tránh Render ngủ
├─ .env.example                # File mẫu biến môi trường
├─ .gitignore                  # Bỏ qua .venv, .env, __pycache__, bytecode
├─ requirements.txt            # Whitelist thư viện đã đóng băng
└─ Procfile                    # Cấu hình khởi chạy trên Render
```

---

## 2. Ranh Giới Quyền Hạn Agent

| Agent | Được sửa | Không được sửa |
|---|---|---|
| **ANTIGRAVITY** | `app/` (trừ `templates/`, `static/`), `db/`, `requirements.txt`, `Procfile`, `.github/`, `.env.example` | `tests/`, `app/templates/`, `app/static/` |
| **CODEX** | `tests/` | Mọi thư mục khác (chỉ đọc và báo lỗi) |
| **CURSOR** | `app/templates/`, `app/static/` | `app/services/`, `db/`, `tests/` |

---

## 3. Lệnh Thao Tác Chuẩn

```powershell
# Kích hoạt môi trường ảo
.venv\Scripts\Activate.ps1

# Chạy server phát triển
flask --app app run --port 5000

# Chạy toàn bộ test suite (CODEX)
py -m unittest discover -s tests -v
```
