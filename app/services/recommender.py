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

    # 4. Tính điểm Hybrid
    scored_list: list[ScoredDestination] = []
    for d in province_dests:
        cb_val = float(cb_scores.get(d.id, 0.0))
        if d.id in cf_scores:
            cf_val = float(cf_scores[d.id])
            final_score = HYBRID_WEIGHT_CB * cb_val + HYBRID_WEIGHT_CF * cf_val
            cf_record = cf_val
        else:
            final_score = cb_val
            cf_record = None

        scored_list.append(
            ScoredDestination(
                destination=d,
                score=final_score,
                cb_score=cb_val,
                cf_score=cf_record,
            )
        )

    # 5. Sắp xếp: score giảm dần, id tăng dần khi hòa điểm
    scored_list.sort(key=lambda item: (-item.score, item.destination.id))
    return scored_list
