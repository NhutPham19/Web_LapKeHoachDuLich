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
    TRAVEL_SPEED_KMH,
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
    """
    Kiểm tra địa điểm có mở cửa trong suốt khoảng thời gian tham quan (Finding #21).
    - d.opening_hours is None -> luôn mở (True).
    - {} rỗng -> lỗi dữ liệu -> False.
    - Hỗ trợ nhiều ca cách nhau dấu phẩy: "08:00-11:30,13:30-17:00".
    - Hỗ trợ mở cả ngày: "00:00-24:00" hoặc "00:00-00:00".
    - Hỗ trợ qua nửa đêm: "18:00-02:00".
    """
    if d.opening_hours is None:
        return True
    if not isinstance(d.opening_hours, dict) or len(d.opening_hours) == 0:
        return False

    weekday_key = WEEKDAY_KEYS[check_date.weekday()]
    if weekday_key not in d.opening_hours:
        return False

    hours_str = d.opening_hours[weekday_key]
    if not hours_str or not isinstance(hours_str, str):
        return False

    end_minutes = start_minutes + int(round(duration_hours * 60))

    shifts = [s.strip() for s in hours_str.split(",") if s.strip()]
    for shift in shifts:
        if "-" not in shift:
            continue
        try:
            parts = shift.split("-")
            open_str, close_str = parts[0].strip(), parts[1].strip()
            open_min = _time_str_to_minutes(open_str)
            close_min = _time_str_to_minutes(close_str)

            # Cả ngày 24/24
            if open_min == 0 and (close_min == 1440 or close_min == 0):
                return True

            # Đóng qua nửa đêm (ví dụ 18:00-02:00)
            if close_min <= open_min:
                close_min += 1440

            # Ca bao trọn toàn bộ thời gian tham quan
            if open_min <= start_minutes and close_min >= end_minutes:
                return True
        except Exception:
            continue

    return False


def build_itinerary(
    ranked: list[ScoredDestination],
    request: TripRequest,
    weather: list[WeatherDay],
) -> tuple[tuple[DayPlan, ...], list[str]]:
    """
    Xây dựng lịch trình theo thuật toán Greedy (1.G.4, Findings #15, #17, #18, #19, #21):
    - Tối đa MAX_ITEMS_PER_SLOT (2) mỗi slot.
    - Thời gian di chuyển = travel_km / TRAVEL_SPEED_KMH (30 km/h) cộng vào quỹ thời gian slot.
    - Item 1 slot đầu ngày: điểm cao nhất hợp lệ.
    - Item 1 các slot sau: lấy top-M (M = 2 * số chỗ trống) điểm còn lại, chọn điểm gần nhất với điểm cuối của slot trước.
    - Item 2 trong slot: điểm gần nhất với Item 1.
    - Ràng buộc: giờ mở cửa (nhiều ca/qua đêm), sức chứa slot (tính cả di chuyển), chưa dùng trong chuyến đi.
    - Ràng buộc ngân sách vé mỗi ngày: <= allocation["ve_vao_cua"] // days (hết ứng viên mới fallback + warning).
    - Thời tiết: mưa hoặc is_severe ưu tiên indoor, hết indoor mới dùng outdoor + warning; slot thiếu dữ liệu (None) coi như không ràng buộc.
    """
    from app.services import budget

    weather_by_date = {w.date: w for w in weather}
    used_dest_ids: set[int] = set()
    warnings: list[str] = []
    day_plans: list[DayPlan] = []

    slot_names_vi = {"morning": "sáng", "afternoon": "chiều", "evening": "tối"}

    # Ngân sách vé tối đa mỗi ngày (Finding #18)
    alloc = budget.calc_allocation(request.budget)
    daily_ticket_limit = alloc.get("ve_vao_cua", 0) // request.days

    for d_idx in range(request.days):
        day_num = d_idx + 1
        cur_date = request.start_date + timedelta(days=d_idx)
        cur_weather = weather_by_date.get(cur_date)

        if cur_weather and cur_weather.is_severe:
            warnings.append(
                f"Cảnh báo: Ngày {day_num} ({cur_date.strftime('%d/%m/%Y')}) có thời tiết cực đoan ({cur_weather.condition}). Hãy cẩn thận khi tham quan."
            )

        day_items: list[ItineraryItem] = []
        prev_slot_last_dest: Optional[Destination] = None
        day_ticket_cost = 0
        budget_warned_today = False

        for slot in TIME_SLOTS:
            slot_capacity = float(SLOT_HOURS[slot])
            slot_start_min = _time_str_to_minutes(SLOT_START[slot])
            used_duration = 0.0
            slot_items: list[ItineraryItem] = []

            rain_val = cur_weather.rain_prob.get(slot) if cur_weather else None
            is_rainy = rain_val is not None and rain_val >= RAIN_THRESHOLD

            for order in range(1, MAX_ITEMS_PER_SLOT + 1):
                prev_dest: Optional[Destination] = (
                    prev_slot_last_dest if order == 1 else slot_items[-1].destination
                )

                # Tìm ứng viên cơ bản
                basic_candidates: list[Destination] = []
                for sd in ranked:
                    dest = sd.destination
                    if dest.id in used_dest_ids:
                        continue

                    travel_km = 0.0
                    travel_time_hours = 0.0
                    if prev_dest is not None:
                        travel_km = haversine_km(
                            prev_dest.latitude,
                            prev_dest.longitude,
                            dest.latitude,
                            dest.longitude,
                        )
                        travel_time_hours = travel_km / TRAVEL_SPEED_KMH

                    additional_time = dest.duration_hours
                    if order > 1:
                        additional_time += travel_time_hours

                    if used_duration + additional_time > slot_capacity:
                        continue

                    cand_start_min = slot_start_min + int(round(used_duration * 60))
                    if order > 1:
                        cand_start_min += int(round(travel_time_hours * 60))

                    if not _is_open(dest, cur_date, cand_start_min, dest.duration_hours):
                        continue

                    basic_candidates.append(dest)

                if not basic_candidates:
                    break

                # Lọc theo ngân sách vé ngày (Finding #18)
                def get_cost(d: Destination) -> int:
                    u_price = (
                        d.ticket_price
                        if d.ticket_price > 0
                        else TICKET_PRICE_BY_RANGE.get(d.price_range, 0)
                    )
                    return u_price * request.num_people

                budget_candidates = [
                    c
                    for c in basic_candidates
                    if (day_ticket_cost + get_cost(c)) <= daily_ticket_limit
                ]

                if budget_candidates:
                    cands = budget_candidates
                else:
                    cands = basic_candidates
                    if not budget_warned_today and any(
                        (day_ticket_cost + get_cost(c)) > daily_ticket_limit
                        for c in basic_candidates
                    ):
                        budget_warned_today = True

                # Lọc theo thời tiết mưa
                if is_rainy:
                    indoor_cands = [c for c in cands if not c.is_outdoor]
                    target_cands = indoor_cands if indoor_cands else cands
                else:
                    target_cands = cands

                selected_dest: Optional[Destination] = None
                travel_km_val = 0.0

                if order == 1:
                    if prev_slot_last_dest is None:
                        selected_dest = target_cands[0]
                        travel_km_val = 0.0
                    else:
                        slots_left = MAX_ITEMS_PER_SLOT - order + 1
                        top_m_limit = min(len(target_cands), 2 * slots_left)
                        top_m = list(target_cands[:top_m_limit])
                        top_m.sort(
                            key=lambda d: haversine_km(
                                prev_slot_last_dest.latitude,
                                prev_slot_last_dest.longitude,
                                d.latitude,
                                d.longitude,
                            )
                        )
                        selected_dest = top_m[0]
                        travel_km_val = haversine_km(
                            prev_slot_last_dest.latitude,
                            prev_slot_last_dest.longitude,
                            selected_dest.latitude,
                            selected_dest.longitude,
                        )
                else:
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
                    travel_km_val = haversine_km(
                        first_dest.latitude,
                        first_dest.longitude,
                        selected_dest.latitude,
                        selected_dest.longitude,
                    )
                    used_duration += travel_km_val / TRAVEL_SPEED_KMH

                if is_rainy and selected_dest.is_outdoor:
                    warnings.append(
                        f"Ngày {day_num} buổi {slot_names_vi.get(slot, slot)} có khả năng mưa cao nhưng phải xếp địa điểm ngoài trời ({selected_dest.name})."
                    )

                est_cost = get_cost(selected_dest)
                day_ticket_cost += est_cost

                item_obj = ItineraryItem(
                    destination=selected_dest,
                    day_number=day_num,
                    time_slot=slot,
                    order_in_slot=order,
                    estimated_cost=est_cost,
                    notes="",
                    travel_km_from_prev=round(travel_km_val, 2),
                )
                slot_items.append(item_obj)
                used_dest_ids.add(selected_dest.id)
                used_duration += selected_dest.duration_hours

            if len(slot_items) == 0:
                warnings.append(
                    f"Không đủ địa điểm phù hợp cho ngày {day_num} buổi {slot_names_vi.get(slot, slot)}."
                )
            else:
                prev_slot_last_dest = slot_items[-1].destination

            day_items.extend(slot_items)

        if budget_warned_today and day_ticket_cost > daily_ticket_limit:
            warnings.append(
                f"Ngày {day_num}: Chi phí vé thực tế ({day_ticket_cost:,} VNĐ) vượt định mức phân bổ ngày ({daily_ticket_limit:,} VNĐ)."
            )

        day_plans.append(
            DayPlan(
                day_number=day_num,
                date=cur_date,
                items=tuple(day_items),
                weather=cur_weather,
            )
        )

    return tuple(day_plans), warnings
