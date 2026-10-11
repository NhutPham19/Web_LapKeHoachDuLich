from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Protocol

# 1.B Hằng số dùng chung
INTERESTS = ("thien_nhien", "bien", "nui", "van_hoa", "lich_su",
             "am_thuc", "mua_sam", "vui_choi", "yen_tinh")
TRAVEL_STYLES = ("tiet_kiem", "thoai_mai", "sang_trong")
TIME_SLOTS = ("morning", "afternoon", "evening")
TEST_PROVINCES = ("Đà Lạt", "Hội An", "Phú Quốc")
PROVINCE_COORDS = {            # Nguồn sự thật duy nhất cho 6 Hub điểm đến và OpenWeatherMap
    "Đà Lạt": (11.9404, 108.4583),
    "Hội An": (15.8801, 108.3380),
    "Phú Quốc": (10.2899, 103.9840),
    "Hà Nội": (21.0285, 105.8542),
    "Đà Nẵng": (16.0544, 108.2022),
    "TP. Hồ Chí Minh": (10.8231, 106.6297),
}
PROVINCES: tuple[str, ...] = tuple(PROVINCE_COORDS.keys())
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")   # date.weekday() → key

SLOT_START = {"morning": "08:00", "afternoon": "13:30", "evening": "18:00"}
SLOT_HOURS = {"morning": 3.5, "afternoon": 4.0, "evening": 3.0}    # sức chứa mỗi buổi
MAX_ITEMS_PER_SLOT = 2
RAIN_THRESHOLD = 0.5                      # rain_prob >= ngưỡng → buổi đó ưu tiên indoor
TICKET_PRICE_BY_RANGE = {1: 0, 2: 50_000, 3: 150_000, 4: 300_000}  # VNĐ/người (fallback khi không có ticket_price)
BUDGET_SPLIT = {"luu_tru": 0.35, "an_uong": 0.30, "di_chuyen": 0.15,
                "ve_vao_cua": 0.10, "du_phong": 0.10}
STYLE_PRICE_TARGET = {"tiet_kiem": 2, "thoai_mai": 3, "sang_trong": 4}
HYBRID_WEIGHT_CB, HYBRID_WEIGHT_CF = 0.7, 0.3
CF_K_NEIGHBORS = 10                       # Finding #13: K=10 trong các user đã chấm candidate
CF_MIN_USER_RATINGS = 5                   # user có < 5 đánh giá → bỏ CF (cold start)
CF_MIN_TOTAL_RATINGS = 50                 # toàn hệ thống < 50 đánh giá → bỏ CF
CF_MIN_CORATED_ITEMS = 2                  # Claude 1A: Ngưỡng tối thiểu số item chung để tính tương đồng
CF_SHRINKAGE_LAMBDA = 2.0                 # Claude 1A: Hệ số shrinkage phạt cặp user ít item chung
WEATHER_CACHE_TTL_HOURS = 3
VN_UTC_OFFSET_HOURS = 7
TRAVEL_SPEED_KMH = 30                     # Finding #17: vận tốc di chuyển ước tính đô thị/du lịch
MIN_BUDGET_PER_PERSON_DAY = 300_000       # Finding #22: sàn ngân sách hợp lý
MAX_BUDGET = 1_000_000_000                # Finding #22: trần ngân sách chống tràn số


# 1.C Data types
@dataclass(frozen=True)
class TripRequest:
    province: str                     # ∈ PROVINCES
    start_date: date                  # >= hôm nay (giờ VN)
    days: int                         # 1..7
    budget: int                       # VNĐ tổng
    num_people: int                   # 1..20
    interests: tuple[str, ...]        # ⊆ INTERESTS, >= 1 phần tử, không trùng
    travel_style: str                 # ∈ TRAVEL_STYLES
    user_id: Optional[int] = None

@dataclass(frozen=True)
class Destination:
    id: int
    name: str
    province: str
    latitude: float
    longitude: float
    category_id: int
    price_range: int                  # 1..4 (dùng cho ML)
    noise_level: int                  # 1..5
    duration_hours: float             # > 0
    is_outdoor: bool
    tags: tuple[str, ...] = ()        # phần tử ∈ INTERESTS
    opening_hours: Optional[dict] = None  # {"mon": "08:00-17:00", ...}; None = luôn mở
    ticket_price: int = 0             # Finding #19: giá vé thực tế VNĐ/người (0 = miễn phí)
    category_name: str = ""           # Finding #25: tên danh mục tiện lợi cho hiển thị
    is_active: bool = True            # Finding #23: xóa mềm
    address: str = ""
    description: str = ""
    image_url: str = ""
    avg_rating: Optional[float] = None
    image_public_id: Optional[str] = None
    image_source: str = "placeholder"     # 'wikimedia' | 'placeholder' | 'manual'
    image_author: Optional[str] = None
    image_license: Optional[str] = None
    image_source_url: Optional[str] = None

@dataclass(frozen=True)
class ScoredDestination:
    destination: Destination
    score: float                      # 0..1, điểm cuối (hybrid)
    cb_score: float                   # 0..1
    cf_score: Optional[float] = None  # 0..1; None nếu không có dự đoán CF

@dataclass(frozen=True)
class WeatherDay:
    date: date
    temp_min: float                   # °C
    temp_max: float
    humidity: int                     # %
    rain_prob: dict[str, Optional[float]]  # Finding #15: None nếu thiếu dữ liệu cho slot
    condition: str                    # mô tả tiếng Việt từ API
    is_severe: bool                   # giông bão/mưa to (xem 1.G.5)

@dataclass(frozen=True)
class ItineraryItem:
    destination: Destination
    day_number: int                   # 1..days
    time_slot: str                    # ∈ TIME_SLOTS
    order_in_slot: int                # 1..MAX_ITEMS_PER_SLOT
    estimated_cost: int               # VNĐ, tổng cho cả nhóm
    notes: str = ""
    id: Optional[int] = None          # id dòng itinerary_items khi đã lưu DB
    travel_km_from_prev: float = 0.0  # Finding #17: km cách điểm trước đó

@dataclass(frozen=True)
class DayPlan:
    day_number: int
    date: date
    items: tuple[ItineraryItem, ...]
    weather: Optional[WeatherDay] = None

@dataclass(frozen=True)
class CostBreakdown:
    budget: int
    per_day: int                      # budget // days
    allocation: dict                  # 5 key của BUDGET_SPLIT, tổng == budget
    tickets_estimated: int            # tổng estimated_cost của mọi item
    within_budget: bool               # tickets_estimated <= allocation["ve_vao_cua"]
    per_day_allocation: dict[str, int] = field(default_factory=dict)  # Finding #18

@dataclass(frozen=True)
class TripPlan:
    request: TripRequest
    days: tuple[DayPlan, ...]
    cost: CostBreakdown
    warnings: tuple[str, ...] = ()    # tiếng Việt, hiển thị cho người dùng

@dataclass(frozen=True)
class TripRecord:
    id: int
    user_id: int
    title: str
    status: str                       # "draft" | "confirmed" | "completed"
    is_public: bool
    share_token: Optional[str]
    plan: TripPlan

class Repository(Protocol):
    """Protocol giao tiếp dữ liệu chuẩn cho toàn bộ hệ thống"""
    def get_user_by_email(self, email: str) -> Optional[dict]: ...
    def get_user_by_id(self, user_id: int) -> Optional[dict]: ...
    def create_user(self, email: str, password_hash: str, full_name: str) -> int: ...
    def set_user_admin(self, email: str, is_admin: bool = True) -> bool: ...
    def get_user_preferences(self, user_id: int) -> Optional[dict]: ...
    def save_user_preferences(self, user_id: int, interests: list[str], travel_style: str) -> None: ...
    def list_destinations(self, province: str, active_only: bool = True) -> list[Destination]: ...
    def get_destination(self, dest_id: int) -> Optional[Destination]: ...
    def save_destination(self, data: dict) -> int: ...
    def delete_destination(self, dest_id: int) -> None: ...  # xóa mềm is_active=False
    def list_categories(self) -> list[dict]: ...
    def save_category(self, name: str, icon: str = "") -> int: ...
    def delete_category(self, cat_id: int) -> bool: ...
    def save_trip(self, record: TripRecord) -> int: ...
    def get_trip(self, trip_id: int) -> Optional[TripRecord]: ...
    def get_trip_by_share_token(self, token: str) -> Optional[TripRecord]: ...
    def list_user_trips(self, user_id: int) -> list[TripRecord]: ...
    def update_trip_status(self, trip_id: int, status: str) -> None: ...
    def set_trip_share(self, trip_id: int, is_public: bool, share_token: Optional[str]) -> None: ...
    def delete_trip(self, trip_id: int) -> None: ...
    def add_item(self, trip_id: int, item: ItineraryItem) -> int: ...
    def update_item(self, trip_id: int, item_id: int, fields: dict) -> None: ...
    def delete_item(self, trip_id: int, item_id: int) -> None: ...
    def save_rating(self, user_id: int, destination_id: int, trip_id: int, score: int, review_text: str = "") -> int: ...
    def list_approved_ratings(self) -> list[dict]: ...
    def list_all_ratings_for_admin(self) -> list[dict]: ...
    def approve_rating(self, rating_id: int, approved: bool) -> None: ...
    def get_weather_cache(self, province: str) -> Optional[tuple[str, object]]: ...
    def save_weather_cache(self, province: str, payload_json: str) -> None: ...
    def ping_db(self) -> bool: ...

