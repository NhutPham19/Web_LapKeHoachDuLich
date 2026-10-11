from app.contracts import BUDGET_SPLIT, CostBreakdown, DayPlan, TripRequest


def calc_allocation(budget_total: int) -> dict[str, int]:
    """Phân bổ ngân sách theo tỷ lệ cố định của 5 hạng mục"""
    categories = ("luu_tru", "an_uong", "di_chuyen", "ve_vao_cua")
    allocation = {cat: round(budget_total * BUDGET_SPLIT[cat]) for cat in categories}
    allocated_sum = sum(allocation.values())
    allocation["du_phong"] = budget_total - allocated_sum
    return allocation


def allocate(request: TripRequest, days: tuple[DayPlan, ...]) -> CostBreakdown:
    """
    Phân bổ ngân sách chuyến đi theo 5 hạng mục:
    - Lưu trú (35%), Ăn uống (30%), Di chuyển (15%), Vé vào cửa (10%), Dự phòng (10%).
    - Đảm bảo sum(allocation.values()) == request.budget (xử lý làm tròn).
    - Tính tổng vé ước tính tickets_estimated từ các items và kiểm tra within_budget.
    - Bổ sung per_day_allocation theo Finding #18 (amount // days).
    """
    b = request.budget
    allocation = calc_allocation(b)
    per_day = b // request.days
    per_day_allocation = {cat: amt // request.days for cat, amt in allocation.items()}

    # Tổng chi phí vé ước tính
    tickets_estimated = sum(item.estimated_cost for day in days for item in day.items)
    within_budget = tickets_estimated <= allocation["ve_vao_cua"]

    return CostBreakdown(
        budget=b,
        per_day=per_day,
        allocation=allocation,
        tickets_estimated=tickets_estimated,
        within_budget=within_budget,
        per_day_allocation=per_day_allocation,
    )
