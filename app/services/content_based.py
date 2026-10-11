import numpy as np

try:
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:
    def cosine_similarity(u, v):
        u_arr = np.atleast_2d(u)
        v_arr = np.atleast_2d(v)
        dot = np.dot(u_arr, v_arr.T)
        norm_u = np.linalg.norm(u_arr, axis=1, keepdims=True)
        norm_v = np.linalg.norm(v_arr, axis=1, keepdims=True)
        denom = norm_u * norm_v.T
        with np.errstate(divide="ignore", invalid="ignore"):
            res = np.where(denom > 0, dot / denom, 0.0)
        return res

from app.contracts import INTERESTS, STYLE_PRICE_TARGET, Destination, TripRequest


def build_user_vector(request: TripRequest) -> list[float]:
    """
    Xây dựng vector đặc trưng người dùng 11 chiều:
    - 9 chiều đầu: sở thích theo INTERESTS
    - Chiều 10: giá theo STYLE_PRICE_TARGET
    - Chiều 11: độ ồn (0.0 nếu có yen_tinh, ngược lại 0.5)
    """
    vec = []
    # 9 chiều đầu: INTERESTS
    user_interests_set = set(request.interests)
    for interest in INTERESTS:
        vec.append(1.0 if interest in user_interests_set else 0.0)

    # Chiều 10: giá
    target_price = STYLE_PRICE_TARGET.get(request.travel_style, 2)
    vec.append((target_price - 1.0) / 3.0)

    # Chiều 11: độ ồn
    noise_target = 0.0 if "yen_tinh" in user_interests_set else 0.5
    vec.append(noise_target)

    return vec


def build_item_vector(d: Destination) -> list[float]:
    """
    Xây dựng vector đặc trưng địa điểm 11 chiều:
    - 9 chiều đầu: tags thuộc INTERESTS
    - Chiều 10: (price_range - 1) / 3
    - Chiều 11: (noise_level - 1) / 4
    """
    vec = []
    # 9 chiều đầu: INTERESTS
    item_tags_set = set(d.tags)
    for interest in INTERESTS:
        vec.append(1.0 if interest in item_tags_set else 0.0)

    # Chiều 10: giá
    vec.append((float(d.price_range) - 1.0) / 3.0)

    # Chiều 11: độ ồn
    vec.append((float(d.noise_level) - 1.0) / 4.0)

    return vec


def score(request: TripRequest, destinations: list[Destination]) -> dict[int, float]:
    """
    Tính cosine similarity giữa request và từng địa điểm.
    destination_id -> điểm trong [0, 1]. Nếu vector toàn 0 -> 0.0.
    """
    if not destinations:
        return {}

    user_vec = build_user_vector(request)
    u_arr = np.array(user_vec).reshape(1, -1)

    # Kiểm tra user vector có toàn 0 không
    if np.all(u_arr == 0):
        return {d.id: 0.0 for d in destinations}

    results = {}
    for d in destinations:
        item_vec = build_item_vector(d)
        i_arr = np.array(item_vec).reshape(1, -1)
        if np.all(i_arr == 0):
            results[d.id] = 0.0
            continue

        sim = cosine_similarity(u_arr, i_arr)[0][0]
        # Kẹp trong [0, 1] và làm tròn số float
        clamped_sim = max(0.0, min(1.0, float(sim)))
        results[d.id] = clamped_sim

    return results
