from typing import Optional
import numpy as np

from app.contracts import CF_K_NEIGHBORS, CF_MIN_TOTAL_RATINGS, CF_MIN_USER_RATINGS


def score(
    user_id: Optional[int],
    ratings: list[tuple[int, int, int] | tuple[int, int, float]],
    candidate_ids: list[int],
) -> dict[int, float]:
    """
    Tính điểm dự đoán Collaborative Filtering (KNN user-based):
    Finding #13 & #14:
    - Gộp trùng (user, destination) bằng trung bình.
    - Cold start: Trả {} nếu user_id is None, hoặc số đánh giá của user < 5,
      hoặc tổng số đánh giá của hệ thống < 50.
    - Lấy top-K (K=10) trong những user đã chấm candidate đó có sim > 0.
    - Trừ trung bình user:
      pred = mean_u + sum(w * (r_v - mean_v)) / sum(w)
      Kẹp [1, 5] rồi chuẩn hóa (pred - 1) / 4.
    - Nếu không có user nào đã chấm candidate có sim > 0 hoặc sum(w) == 0:
      candidate vắng mặt trong dict trả về.
    """
    if user_id is None:
        return {}

    # 1. Gộp duplicate ratings (u, d) bằng trung bình (Finding #14)
    grouped: dict[tuple[int, int], list[float]] = {}
    for entry in ratings:
        u, d, r = entry[0], entry[1], float(entry[2])
        grouped.setdefault((u, d), []).append(r)

    merged_ratings: list[tuple[int, int, float]] = [
        (u, d, sum(vals) / len(vals)) for (u, d), vals in grouped.items()
    ]

    # Kiểm tra cold start (Finding #13)
    if len(merged_ratings) < CF_MIN_TOTAL_RATINGS:
        return {}

    user_ratings = [r for (u, d, r) in merged_ratings if u == user_id]
    if len(user_ratings) < CF_MIN_USER_RATINGS:
        return {}

    # 2. Xây dựng ma trận user-item
    user_set = sorted(list({u for u, d, r in merged_ratings}))
    if user_id not in user_set:
        return {}

    dest_set = sorted(list({d for u, d, r in merged_ratings}))
    user_idx_map = {uid: i for i, uid in enumerate(user_set)}
    dest_idx_map = {did: j for j, did in enumerate(dest_set)}

    matrix = np.zeros((len(user_set), len(dest_set)), dtype=float)
    for u, d, r in merged_ratings:
        matrix[user_idx_map[u], dest_idx_map[d]] = r

    target_u_idx = user_idx_map[user_id]
    target_vec = matrix[target_u_idx]

    # Tính mean rating của mỗi user (chỉ tính trên các item đã rating > 0)
    user_means = np.zeros(len(user_set), dtype=float)
    for i in range(len(user_set)):
        rated_items = matrix[i][matrix[i] > 0]
        user_means[i] = float(np.mean(rated_items)) if len(rated_items) > 0 else 0.0

    mean_u = user_means[target_u_idx]

    # 3. Tính độ tương đồng cosine giữa target_user và tất cả users khác
    dot_products = np.dot(matrix, target_vec).flatten()
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(target_vec)
    with np.errstate(divide="ignore", invalid="ignore"):
        similarities = np.where(norms > 0, dot_products / norms, 0.0)

    # Loại bỏ chính target_user
    similarities[target_u_idx] = 0.0

    # 4. Dự đoán điểm cho từng candidate_id (Finding #13)
    results: dict[int, float] = {}
    for c_id in candidate_ids:
        if c_id not in dest_idx_map:
            continue
        c_idx = dest_idx_map[c_id]

        # Lấy những user đã chấm candidate c_idx và có similarity > 0
        candidate_reviewers = [
            v_idx
            for v_idx in range(len(user_set))
            if v_idx != target_u_idx and matrix[v_idx, c_idx] > 0 and similarities[v_idx] > 0
        ]

        if not candidate_reviewers:
            continue

        # Sắp xếp giảm dần theo similarity và lấy top K (K=10)
        candidate_reviewers.sort(key=lambda idx: similarities[idx], reverse=True)
        top_k = candidate_reviewers[:CF_K_NEIGHBORS]

        sum_w = float(sum(similarities[v_idx] for v_idx in top_k))
        if sum_w <= 0.0:
            continue

        weighted_dev = float(
            sum(
                similarities[v_idx] * (matrix[v_idx, c_idx] - user_means[v_idx])
                for v_idx in top_k
            )
        )

        pred = mean_u + (weighted_dev / sum_w)
        # Kẹp [1, 5]
        pred_clamped = max(1.0, min(5.0, pred))
        # Chuẩn hóa về [0, 1]
        normalized_score = (pred_clamped - 1.0) / 4.0
        results[c_id] = float(normalized_score)

    return results
