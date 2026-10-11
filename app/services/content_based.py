import numpy as np

from app.contracts import INTERESTS, STYLE_PRICE_TARGET, Destination, TripRequest


def score(request: TripRequest, destinations: list[Destination]) -> dict[int, float]:
    """
    Tính điểm Content-Based theo đề xuất Finding #12 của Lead Architect:
    - Cosine similarity trên 9 chiều sở thích INTERESTS
    - price_fit = 1 - abs(price_range - STYLE_PRICE_TARGET[style]) / 3
    - noise_fit = 1 - abs(noise_level - noise_target) / 4 (target=1 nếu yen_tinh, else 3)
    - cb = 0.7 * cos + 0.15 * price_fit + 0.15 * noise_fit
    """
    if not destinations:
        return {}

    user_interests_set = set(request.interests)
    u_interests = np.array([1.0 if i in user_interests_set else 0.0 for i in INTERESTS], dtype=float)
    norm_u = np.linalg.norm(u_interests)

    target_price = STYLE_PRICE_TARGET.get(request.travel_style, 2)
    noise_target = 1.0 if "yen_tinh" in user_interests_set else 3.0

    results = {}
    for d in destinations:
        item_tags_set = set(d.tags)
        i_interests = np.array([1.0 if i in item_tags_set else 0.0 for i in INTERESTS], dtype=float)
        norm_i = np.linalg.norm(i_interests)

        if norm_u > 0 and norm_i > 0:
            cos_sim = float(np.dot(u_interests, i_interests) / (norm_u * norm_i))
            cos_sim = max(0.0, min(1.0, cos_sim))
        else:
            cos_sim = 0.0

        price_fit = 1.0 - abs(float(d.price_range) - float(target_price)) / 3.0
        price_fit = max(0.0, min(1.0, price_fit))

        noise_fit = 1.0 - abs(float(d.noise_level) - float(noise_target)) / 4.0
        noise_fit = max(0.0, min(1.0, noise_fit))

        cb = 0.7 * cos_sim + 0.15 * price_fit + 0.15 * noise_fit
        results[d.id] = round(max(0.0, min(1.0, cb)), 4)

    return results

