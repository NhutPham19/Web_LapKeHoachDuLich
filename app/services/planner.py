from app.contracts import Destination, TripPlan, TripRequest, WeatherDay
from app.services import budget, itinerary, recommender


def generate_plan(
    request: TripRequest,
    destinations: list[Destination],
    ratings: list[tuple[int, int, int]],
    weather: list[WeatherDay],
) -> TripPlan:
    """
    Hàm thuần điều phối toàn bộ luồng tạo kế hoạch chuyến đi (1.D, 1.G):
    1. Gợi ý xếp hạng địa điểm (Hybrid Recommender)
    2. Sắp xếp lịch trình theo ngày/buổi (Greedy Itinerary)
    3. Phân bổ ngân sách & chi phí (Budget Allocation)
    4. Tổng hợp cảnh báo (thời tiết, thiếu điểm, vượt ngân sách vé)
    """
    # 1. Gợi ý xếp hạng địa điểm
    ranked = recommender.recommend(request, destinations, ratings)

    # 2. Xếp lịch trình tham lam
    day_plans, warnings = itinerary.build_itinerary(ranked, request, weather)

    # 3. Phân bổ ngân sách
    cost = budget.allocate(request, day_plans)

    # 4. Kiểm tra cảnh báo ngân sách vé
    if not cost.within_budget:
        ticket_budget = cost.allocation.get("ve_vao_cua", 0)
        warnings.append(
            f"Cảnh báo ngân sách: Tiền vé dự kiến ({cost.tickets_estimated:,} VNĐ) vượt quá định mức vé vào cửa ({ticket_budget:,} VNĐ)."
        )

    return TripPlan(
        request=request,
        days=day_plans,
        cost=cost,
        warnings=tuple(warnings),
    )
