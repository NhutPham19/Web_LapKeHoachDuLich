from app.contracts import (
    HYBRID_WEIGHT_CB,
    HYBRID_WEIGHT_CF,
    Destination,
    ScoredDestination,
    TripRequest,
)
from app.services import collaborative, content_based


def recommend(
    request: TripRequest,
    destinations: list[Destination],
    ratings: list[tuple[int, int, int]],
) -> list[ScoredDestination]:
    """
    Gợi ý địa điểm kết hợp Content-Based và Collaborative Filtering (Hybrid).
    - Chỉ xét các destinations cùng tỉnh (request.province).
    - Có CF: score = 0.7 * cb + 0.3 * cf
    - Không có CF: score = cb, cf_score = None
    - Sắp xếp: score giảm dần; nếu hòa điểm: id tăng dần.
    """
    # 1. Lọc theo tỉnh
    province_dests = [d for d in destinations if d.province == request.province]
    if not province_dests:
        return []

    # 2. Tính điểm Content-Based
    cb_scores = content_based.score(request, province_dests)

    # 3. Tính điểm Collaborative Filtering
    candidate_ids = [d.id for d in province_dests]
    cf_scores = collaborative.score(request.user_id, ratings, candidate_ids)

    # 4. Chuẩn hóa min-max cb và cf trong tập candidate trước khi trộn (Finding #12)
    cb_vals = [cb_scores.get(d.id, 0.0) for d in province_dests]
    min_cb = min(cb_vals) if cb_vals else 0.0
    max_cb = max(cb_vals) if cb_vals else 1.0

    cb_norm: dict[int, float] = {}
    for d in province_dests:
        val = cb_scores.get(d.id, 0.0)
        if max_cb > min_cb:
            cb_norm[d.id] = (val - min_cb) / (max_cb - min_cb)
        else:
            cb_norm[d.id] = 1.0 if val > 0 else 0.0

    cf_norm: dict[int, float] = {}
    if cf_scores:
        cf_vals = list(cf_scores.values())
        min_cf = min(cf_vals)
        max_cf = max(cf_vals)
        for did, val in cf_scores.items():
            if max_cf > min_cf:
                cf_norm[did] = (val - min_cf) / (max_cf - min_cf)
            else:
                cf_norm[did] = 1.0 if val > 0 else 0.0

    scored_list: list[ScoredDestination] = []
    for d in province_dests:
        cb_raw = float(cb_scores.get(d.id, 0.0))
        cb_val = float(cb_norm.get(d.id, 0.0))
        if d.id in cf_norm:
            cf_val = float(cf_norm[d.id])
            final_score = HYBRID_WEIGHT_CB * cb_val + HYBRID_WEIGHT_CF * cf_val
            cf_record = float(cf_scores[d.id])
        else:
            final_score = cb_val
            cf_record = None

        scored_list.append(
            ScoredDestination(
                destination=d,
                score=final_score,
                cb_score=cb_raw,
                cf_score=cf_record,
            )
        )

    # 5. Sắp xếp: score giảm dần, id tăng dần khi hòa điểm
    scored_list.sort(key=lambda item: (-item.score, item.destination.id))
    return scored_list
