from dataclasses import dataclass
from datetime import date
from typing import Optional

# 1.B Hằng số dùng chung
INTERESTS = ("thien_nhien", "bien", "nui", "van_hoa", "lich_su",
             "am_thuc", "mua_sam", "vui_choi", "yen_tinh")
TRAVEL_STYLES = ("tiet_kiem", "thoai_mai", "sang_trong")
TIME_SLOTS = ("morning", "afternoon", "evening")
PROVINCES = ("Đà Lạt", "Hội An", "Phú Quốc")
PROVINCE_COORDS = {            # dùng gọi OpenWeatherMap
    "Đà Lạt": (11.9404, 108.4583),
    "Hội An": (15.8801, 108.3380),
    "Phú Quốc": (10.2899, 103.9840),
}
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")   # date.weekday() → key

SLOT_START = {"morning": "08:00", "afternoon": "13:30", "evening": "18:00"}
SLOT_HOURS = {"morning": 3.5, "afternoon": 4.0, "evening": 3.0}    # sức chứa mỗi buổi
MAX_ITEMS_PER_SLOT = 2
RAIN_THRESHOLD = 0.5                      # rain_prob >= ngưỡng → buổi đó ưu tiên indoor
TICKET_PRICE_BY_RANGE = {1: 0, 2: 50_000, 3: 150_000, 4: 300_000}  # VNĐ/người
BUDGET_SPLIT = {"luu_tru": 0.35, "an_uong": 0.30, "di_chuyen": 0.15,
                "ve_vao_cua": 0.10, "du_phong": 0.10}
STYLE_PRICE_TARGET = {"tiet_kiem": 2, "thoai_mai": 3, "sang_trong": 4}
HYBRID_WEIGHT_CB, HYBRID_WEIGHT_CF = 0.7, 0.3
CF_K_NEIGHBORS = 5
CF_MIN_USER_RATINGS = 5                   # user có < 5 đánh giá → bỏ CF (cold start)
CF_MIN_TOTAL_RATINGS = 50                 # toàn hệ thống < 50 đánh giá → bỏ CF
WEATHER_CACHE_TTL_HOURS = 3
VN_UTC_OFFSET_HOURS = 7


# 1.C Data types
@dataclass(frozen=True)
class TripRequest:
    province: str                     # ∈ PROVINCES
    start_date: date                  # >= hôm nay
    days: int                         # 1..7
    budget: int                       # VNĐ tổng, >= 100_000
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
    price_range: int                  # 1..4
    noise_level: int                  # 1..5
    duration_hours: float             # > 0
    is_outdoor: bool
    tags: tuple[str, ...]             # phần tử ∈ INTERESTS
    opening_hours: Optional[dict]     # {"mon": "08:00-17:00", ...}; None = luôn mở;
                                      # thiếu key của ngày đó = đóng cửa ngày đó
    address: str = ""
    description: str = ""
    image_url: str = ""
    avg_rating: Optional[float] = None

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
    rain_prob: dict                   # {"morning": 0..1, "afternoon": 0..1, "evening": 0..1}
    condition: str                    # mô tả tiếng Việt từ API
    is_severe: bool                   # giông bão (xem 1.G.5)

@dataclass(frozen=True)
class ItineraryItem:
    destination: Destination
    day_number: int                   # 1..days
    time_slot: str                    # ∈ TIME_SLOTS
    order_in_slot: int                # 1..MAX_ITEMS_PER_SLOT
    estimated_cost: int               # VNĐ, tổng cho cả nhóm
    notes: str = ""
    id: Optional[int] = None          # id dòng itinerary_items khi đã lưu DB

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
