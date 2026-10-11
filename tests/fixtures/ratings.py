"""Ratings DỮ LIỆU GIẢ LẬP cho các test collaborative filtering."""

NATURE_USERS = (101, 102, 103, 104, 105)
CULTURE_USERS = (201, 202, 203, 204, 205)
USER_GROUPS = {
    "nature_quiet": {"users": NATURE_USERS, "interests": ("thien_nhien", "bien", "nui", "yen_tinh")},
    "culture_lively": {"users": CULTURE_USERS, "interests": ("van_hoa", "lich_su", "am_thuc", "mua_sam", "vui_choi")},
}
NATURE_DESTINATIONS = (1, 4, 5, 9, 11, 2)
CULTURE_DESTINATIONS = (3, 6, 7, 8, 10, 12)

# (user_id, destination_id, score): 120 ratings có chủ đích, hai nhóm trái sở thích.
SYNTHETIC_RATINGS = [
    (user_id, destination_id, 5) for user_id in NATURE_USERS for destination_id in NATURE_DESTINATIONS
] + [
    (user_id, destination_id, 1) for user_id in NATURE_USERS for destination_id in CULTURE_DESTINATIONS
] + [
    (user_id, destination_id, 5) for user_id in CULTURE_USERS for destination_id in CULTURE_DESTINATIONS
] + [
    (user_id, destination_id, 1) for user_id in CULTURE_USERS for destination_id in NATURE_DESTINATIONS
]
