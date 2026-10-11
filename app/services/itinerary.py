import math
from datetime import date, timedelta
from typing import Optional

from app.contracts import (
    MAX_ITEMS_PER_SLOT,
    RAIN_THRESHOLD,
    SLOT_HOURS,
    SLOT_START,
    TICKET_PRICE_BY_RANGE,
    TIME_SLOTS,
    WEEKDAY_KEYS,
    DayPlan,
    Destination,
    ItineraryItem,
    ScoredDestination,
    TripRequest,
    WeatherDay,
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Tính khoảng cách đại vòng tròn (Haversine) giữa 2 điểm GPS tính bằng km.
    Bán kính Trái Đất R = 6371.0 km.
    """
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def _time_str_to_minutes(t_str: str) -> int:
    parts = t_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _is_open(d: Destination, check_date: date, start_minutes: int, duration_hours: float) -> bool:
    if d.opening_hours is None:
        return True

    weekday_key = WEEKDAY_KEYS[check_date.weekday()]
    if weekday_key not in d.opening_hours:
        return False

    hours_range = d.opening_hours[weekday_key]
    if not hours_range or "-" not in hours_range:
        return False

    try:
        open_str, close_str = hours_range.split("-")
        open_min = _time_str_to_minutes(open_str.strip())
        close_min = _time_str_to_minutes(close_str.strip())
        end_min = start_minutes + int(duration_hours * 60)
        return open_min <= start_minutes and close_min >= end_min
    except Exception:
        return False


def build_itinerary(
    ranked: list[ScoredDestination],
    request: TripRequest,
    weather: list[WeatherDay],
) -> tuple[tuple[DayPlan, ...], list[str]]:
    """
    Xây dựng lịch trình theo thuật toán Greedy (1.G.4):
    - Tối đa MAX_ITEMS_PER_SLOT (2) mỗi slot.
    - Item 1: điểm cao nhất hợp lệ; Item 2: điểm gần nhất với Item 1 hợp lệ.
    - Ràng buộc: giờ mở cửa, sức chứa slot, chưa dùng.
    - Thời tiết: mưa ưu tiên indoor, hết indoor thì dùng outdoor + warning.
    - Cảnh báo thời tiết xấu nếu is_severe.
    """
    weather_by_date = {w.date: w for w in weather}
    used_dest_ids: set[int] = set()
    warnings: list[str] = []
    day_plans: list[DayPlan] = []

    # Map chuyển đổi tên slot tiếng Anh sang tiếng Việt cho warning
    slot_names_vi = {"morning": "sáng", "afternoon": "chiều", "evening": "tối"}

    for d_idx in range(request.days):
        day_num = d_idx + 1
        cur_date = request.start_date + timedelta(days=d_idx)
        cur_weather = weather_by_date.get(cur_date)

        # Cảnh báo thời tiết nguy hiểm
        if cur_weather and cur_weather.is_severe:
            warnings.append(
                f"Cảnh báo: Ngày {day_num} ({cur_date.strftime('%d/%m/%Y')}) có thời tiết cực đoan ({cur_weather.condition}). Hãy cẩn thận khi tham quan."
            )

        day_items: list[ItineraryItem] = []

        for slot in TIME_SLOTS:
            slot_capacity = SLOT_HOURS[slot]
            slot_start_min = _time_str_to_minutes(SLOT_START[slot])
            used_duration = 0.0
            slot_items: list[ItineraryItem] = []

            rain_prob = cur_weather.rain_prob.get(slot, 0.0) if cur_weather else 0.0
            is_rainy = rain_prob >= RAIN_THRESHOLD

            for order in range(1, MAX_ITEMS_PER_SLOT + 1):
                cur_start_min = slot_start_min + int(used_duration * 60)

                # Tìm các ứng viên thỏa mãn các điều kiện cơ bản
                candidates: list[Destination] = []
                for sd in ranked:
                    dest = sd.destination
                    if dest.id in used_dest_ids:
                        continue
                    if used_duration + dest.duration_hours > slot_capacity:
                        continue
                    if not _is_open(dest, cur_date, cur_start_min, dest.duration_hours):
                        continue
                    candidates.append(dest)

                if not candidates:
                    break

                # Lọc ưu tiên thời tiết mưa: ưu tiên indoor
                selected_dest: Optional[Destination] = None
                if is_rainy:
                    indoor_cands = [c for c in candidates if not c.is_outdoor]
                    if indoor_cands:
                        target_cands = indoor_cands
                    else:
                        target_cands = candidates
                        # Warning vì phải đi ngoài trời trong buổi mưa
                else:
                    target_cands = candidates

                if order == 1:
                    # Item đầu: Điểm cao nhất trong ranked
                    selected_dest = target_cands[0]
                    if is_rainy and selected_dest.is_outdoor:
                        warnings.append(
                            f"Ngày {day_num} buổi {slot_names_vi.get(slot, slot)} có khả năng mưa cao nhưng phải xếp địa điểm ngoài trời ({selected_dest.name})."
                        )
                else:
                    # Item thứ 2: Điểm gần nhất với item đầu
                    first_dest = slot_items[0].destination
                    target_cands.sort(
                        key=lambda d: haversine_km(
                            first_dest.latitude,
                            first_dest.longitude,
                            d.latitude,
                            d.longitude,
                        )
                    )
                    selected_dest = target_cands[0]
                    if is_rainy and selected_dest.is_outdoor:
                        warnings.append(
                            f"Ngày {day_num} buổi {slot_names_vi.get(slot, slot)} có khả năng mưa cao nhưng phải xếp địa điểm ngoài trời ({selected_dest.name})."
                        )

                # Tính chi phí vé
                ticket_unit = TICKET_PRICE_BY_RANGE.get(selected_dest.price_range, 0)
                est_cost = ticket_unit * request.num_people

                item_obj = ItineraryItem(
                    destination=selected_dest,
                    day_number=day_num,
                    time_slot=slot,
                    order_in_slot=order,
                    estimated_cost=est_cost,
                    notes="",
                )
                slot_items.append(item_obj)
                used_dest_ids.add(selected_dest.id)
                used_duration += selected_dest.duration_hours

            if len(slot_items) == 0:
                warnings.append(
                    f"Không đủ địa điểm phù hợp cho ngày {day_num} buổi {slot_names_vi.get(slot, slot)}."
                )

            day_items.extend(slot_items)

        day_plans.append(
            DayPlan(
                day_number=day_num,
                date=cur_date,
                items=tuple(day_items),
                weather=cur_weather,
            )
        )

    return tuple(day_plans), warnings
