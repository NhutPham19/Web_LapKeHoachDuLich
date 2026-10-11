from app.contracts import BUDGET_SPLIT, CostBreakdown, DayPlan, TripRequest


def allocate(request: TripRequest, days: tuple[DayPlan, ...]) -> CostBreakdown:
    """
    Phân bổ ngân sách chuyến đi theo 5 hạng mục:
    - Lưu trú (35%), Ăn uống (30%), Di chuyển (15%), Vé vào cửa (10%), Dự phòng (10%).
    - Đảm bảo sum(allocation.values()) == request.budget (xử lý làm tròn).
    - Tính tổng vé ước tính tickets_estimated từ các items và kiểm tra within_budget.
    """
    b = request.budget

    # 4 khoản đầu theo tỷ lệ làm tròn
    categories = ("luu_tru", "an_uong", "di_chuyen", "ve_vao_cua")
    allocation = {cat: round(b * BUDGET_SPLIT[cat]) for cat in categories}

    # Dự phòng là phần còn lại để bảo đảm tổng đúng 100%
    allocated_sum = sum(allocation.values())
    allocation["du_phong"] = b - allocated_sum

    per_day = b // request.days

    # Tổng chi phí vé ước tính
    tickets_estimated = sum(item.estimated_cost for day in days for item in day.items)
    within_budget = tickets_estimated <= allocation["ve_vao_cua"]

    return CostBreakdown(
        budget=b,
        per_day=per_day,
        allocation=allocation,
        tickets_estimated=tickets_estimated,
        within_budget=within_budget,
    )
