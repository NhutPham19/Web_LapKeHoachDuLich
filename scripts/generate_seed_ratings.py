import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SEED = 42
TOTAL_USERS = 50
MIN_RATINGS_PER_USER = 10
MAX_RATINGS_PER_USER = 16

HUBS = ["Đà Lạt", "Hội An", "Phú Quốc", "Hà Nội", "Đà Nẵng", "TP. Hồ Chí Minh"]

PERSONAS = {
    "nature": {
        "fav_cats": {"Thien nhien"},
        "fav_tags": {"thien_nhien", "bien", "nui", "yen_tinh"},
        "dislike_cats": {"Vui choi"},
        "dislike_noise": 3,
    },
    "culture": {
        "fav_cats": {"Van hoa", "Di tich"},
        "fav_tags": {"van_hoa", "lich_su"},
        "dislike_cats": {"Vui choi"},
        "dislike_noise": 3,
    },
    "food": {
        "fav_cats": {"Am thuc"},
        "fav_tags": {"am_thuc", "mua_sam"},
        "dislike_cats": set(),
        "dislike_noise": 0,
    },
    "entertainment": {
        "fav_cats": {"Vui choi"},
        "fav_tags": {"vui_choi", "bien"},
        "dislike_cats": {"Di tich"},
        "dislike_noise": 1,
    },
}

REVIEW_COMMENTS = {
    5: [
        "Trải nghiệm tuyệt vời, cảnh quan và dịch vụ xuất sắc, nhất định sẽ quay lại!",
        "Không gian vô cùng trong lành và thanh bình, rất đáng ghé thăm.",
        "Món ăn đậm đà bản sắc địa phương, phục vụ nhanh nhẹn và chu đáo.",
        "Điểm đến hấp dẫn, nhiều hoạt động giải trí đặc sắc và sôi động.",
        "Di tích giàu giá trị lịch sử và văn hóa, được bảo tồn rất tốt.",
    ],
    4: [
        "Điểm đến đẹp và sạch sẽ, không khí thoải mái, dịch vụ tốt.",
        "Trải nghiệm rất ổn, tuy nhiên cuối tuần hơi đông khách một chút.",
        "Cảnh quan ấn tượng, chụp ảnh đẹp, đồ ăn và giá vé hợp lý.",
        "Rất phù hợp cho chuyến đi cùng gia đình hoặc bạn bè.",
    ],
    3: [
        "Địa điểm tạm ổn, cảnh quan ở mức vừa phải, giá vé hơi cao so với trải nghiệm.",
        "Dịch vụ ở mức trung bình, vào giờ cao điểm phải xếp hàng khá lâu.",
        "Không quá đặc sắc nhưng cũng là một trải nghiệm có thể thử.",
    ],
    2: [
        "Khá đông đúc và thương mại hóa, không đúng với kỳ vọng ban đầu của mình.",
        "Ồn ào và chen chúc, dịch vụ chưa thực sự chu đáo so với chi phí.",
    ],
    1: [
        "Trải nghiệm không như ý, quá xô bồ và dịch vụ thiếu chuyên nghiệp.",
        "Thất vọng về chất lượng quản lý và bảo tồn tại điểm đến.",
    ],
}


def load_destinations(csv_path: Path):
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        destinations = []
        for idx, row in enumerate(reader, start=1):
            raw_tags = row.get("tags", "[]")
            try:
                tags = json.loads(raw_tags)
            except Exception:
                tags = []
            destinations.append({
                "id": idx,
                "name": row["name"].strip(),
                "province": row["province"].strip(),
                "category": row["category_name"].strip(),
                "noise": int(row.get("noise_level", 2)),
                "tags": set(tags),
            })
    return destinations


def calculate_score(user_persona: str, hybrid_secondary: str | None, dest: dict) -> int:
    primary = PERSONAS[user_persona]
    is_primary_fav = (
        dest["category"] in primary["fav_cats"]
        or bool(dest["tags"] & primary["fav_tags"])
    )
    is_primary_dislike = (
        dest["category"] in primary["dislike_cats"]
        or (primary["dislike_noise"] > 0 and dest["noise"] >= primary["dislike_noise"])
    )

    is_sec_fav = False
    if hybrid_secondary:
        sec = PERSONAS[hybrid_secondary]
        is_sec_fav = (
            dest["category"] in sec["fav_cats"]
            or bool(dest["tags"] & sec["fav_tags"])
        )

    if is_primary_fav and is_sec_fav:
        base = 4.8
    elif is_primary_fav:
        base = 4.5
    elif is_sec_fav:
        base = 4.2
    elif is_primary_dislike:
        base = 1.8
    else:
        base = 3.4

    # Thêm nhiễu ngẫu nhiên nhẹ
    score_val = base + random.gauss(0, 0.45)
    score_clamped = max(1, min(5, int(round(score_val))))
    return score_clamped


def generate_ratings():
    random.seed(SEED)
    root_dir = Path(__file__).resolve().parent.parent
    dest_path = root_dir / "db" / "seed" / "destinations.csv"
    destinations = load_destinations(dest_path)

    dests_by_hub = defaultdict(list)
    for d in destinations:
        dests_by_hub[d["province"]].append(d)

    # 50 users:
    # 38 pure personas (10 nature, 10 culture, 9 food, 9 entertainment)
    # 12 hybrid personas (3 nature+food, 3 culture+food, 3 ent+food, 3 nature+culture)
    user_configs = []
    # 10 nature
    for i in range(1, 11):
        user_configs.append((i, "nature", None))
    # 10 culture
    for i in range(11, 21):
        user_configs.append((i, "culture", None))
    # 9 food
    for i in range(21, 30):
        user_configs.append((i, "food", None))
    # 9 entertainment
    for i in range(30, 39):
        user_configs.append((i, "entertainment", None))
    # 12 hybrid
    for i in range(39, 42):
        user_configs.append((i, "nature", "food"))
    for i in range(42, 45):
        user_configs.append((i, "culture", "food"))
    for i in range(45, 48):
        user_configs.append((i, "entertainment", "food"))
    for i in range(48, 51):
        user_configs.append((i, "nature", "culture"))

    all_ratings = []
    # Gán hub cho từng user để đảm bảo mật độ co-rated cao
    # Mỗi cặp persona x hub có >= 3 users
    for user_id, persona, hybrid in user_configs:
        # Mỗi user thăm 2 hubs
        hub1 = HUBS[(user_id * 2) % len(HUBS)]
        hub2 = HUBS[(user_id * 2 + 1) % len(HUBS)]
        user_hubs = [hub1, hub2]

        user_candidates = []
        for h in user_hubs:
            user_candidates.extend(dests_by_hub[h])

        # Chọn 10 - 16 destinations trong các hubs của user
        n_ratings = random.randint(MIN_RATINGS_PER_USER, MAX_RATINGS_PER_USER)
        # Ưu tiên chọn các điểm có liên quan đến persona để tăng mật độ giao nhau
        selected_dests = random.sample(user_candidates, min(n_ratings, len(user_candidates)))

        for d in selected_dests:
            score = calculate_score(persona, hybrid, d)
            comments = REVIEW_COMMENTS[score]
            review = random.choice(comments)
            all_ratings.append({
                "user_id": user_id,
                "destination_id": d["id"],
                "score": score,
                "review_text": review,
                "is_approved": True,
            })

    output_csv = root_dir / "db" / "seed" / "ratings.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["user_id", "destination_id", "score", "review_text", "is_approved"]
        )
        writer.writeheader()
        writer.writerows(all_ratings)

    print(f"-> Đã sinh thành công {len(all_ratings)} ratings cho {TOTAL_USERS} users.")
    print(f"-> Lưu tại: {output_csv}")

    # Thống kê nhanh
    scores_dist = Counter(r["score"] for r in all_ratings)
    print(f"Phân bố điểm: {dict(sorted(scores_dist.items()))}")
    ratings_per_dest = Counter(r["destination_id"] for r in all_ratings)
    print(f"Số điểm được chấm: {len(ratings_per_dest)} / {len(destinations)}")
    print(f"Điểm được chấm nhiều nhất: {max(ratings_per_dest.values())}, ít nhất: {min(ratings_per_dest.values())}")
    return len(all_ratings)


if __name__ == "__main__":
    generate_ratings()
