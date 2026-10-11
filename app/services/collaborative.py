from typing import Optional
import numpy as np

from app.contracts import CF_K_NEIGHBORS, CF_MIN_TOTAL_RATINGS, CF_MIN_USER_RATINGS


def score(
    user_id: Optional[int],
    ratings: list[tuple[int, int, int]],
    candidate_ids: list[int],
) -> dict[int, float]:
    """
    Tính điểm dự đoán Collaborative Filtering (KNN user-based):
    - Cold start: Trả {} nếu user_id is None, hoặc số đánh giá của user < 5,
      hoặc tổng số đánh giá của hệ thống < 50.
    - Dự đoán: Với mỗi candidate, trung bình có trọng số rating của các láng giềng
      đã đánh giá candidate đó, chuẩn hóa (score - 1) / 4 về [0, 1].
    - Nếu không có láng giềng nào đánh giá candidate: candidate vắng mặt trong dict.
    """
    # 1. Kiểm tra Cold Start (1.G.2)
    if user_id is None:
        return {}
    if len(ratings) < CF_MIN_TOTAL_RATINGS:
        return {}

    user_ratings = [r for r in ratings if r[0] == user_id]
    if len(user_ratings) < CF_MIN_USER_RATINGS:
        return {}

    # 2. Xây dựng ma trận user-item
    user_set = sorted(list({r[0] for r in ratings}))
    if user_id not in user_set:
        return {}

    dest_set = sorted(list({r[1] for r in ratings}))
    user_idx_map = {uid: i for i, uid in enumerate(user_set)}
    dest_idx_map = {did: j for j, did in enumerate(dest_set)}

    matrix = np.zeros((len(user_set), len(dest_set)), dtype=float)
    for u, d, r in ratings:
        matrix[user_idx_map[u], dest_idx_map[d]] = float(r)

    target_u_idx = user_idx_map[user_id]
    target_vec = matrix[target_u_idx : target_u_idx + 1]

    # 3. Tính độ tương đồng cosine giữa target_user và tất cả users khác
    # Tránh phụ thuộc vào DLL pyd có thể bị chặn bởi Application Control
    dot_products = np.dot(matrix, target_vec.T).flatten()
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(target_vec)
    with np.errstate(divide="ignore", invalid="ignore"):
        similarities = np.where(norms > 0, dot_products / norms, 0.0)

    # Loại bỏ chính target_user
    similarities[target_u_idx] = -1.0

    # Lấy top K láng giềng có similarity lớn nhất
    other_indices = [i for i in range(len(user_set)) if i != target_u_idx]
    if not other_indices:
        return {}

    # Sắp xếp giảm dần theo similarity
    sorted_neighbors = sorted(other_indices, key=lambda idx: similarities[idx], reverse=True)
    top_k_indices = [idx for idx in sorted_neighbors[:CF_K_NEIGHBORS] if similarities[idx] > 0]

    if not top_k_indices:
        return {}

    # 4. Dự đoán điểm cho các candidate_ids
    results = {}
    for c_id in candidate_ids:
        if c_id not in dest_idx_map:
            continue
        c_idx = dest_idx_map[c_id]

        weighted_sum = 0.0
        weight_total = 0.0

        for n_idx in top_k_indices:
            rating_val = matrix[n_idx, c_idx]
            if rating_val > 0:  # Hàng xóm đã đánh giá địa điểm này
                sim_val = float(similarities[n_idx])
                weighted_sum += sim_val * rating_val
                weight_total += sim_val

        if weight_total > 0:
            pred_rating = weighted_sum / weight_total
            # Chuẩn hóa về [0, 1]
            normalized_score = max(0.0, min(1.0, (pred_rating - 1.0) / 4.0))
            results[c_id] = float(normalized_score)

    return results
