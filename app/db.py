import json
import os
from datetime import date, datetime, timedelta
from typing import Optional
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    _PSYCOPG2_ERROR = None
except Exception as _e:
    psycopg2 = None
    RealDictCursor = None
    _PSYCOPG2_ERROR = str(_e)

from app import config
from app.contracts import (
    CostBreakdown,
    DayPlan,
    Destination,
    ItineraryItem,
    TripPlan,
    TripRecord,
    TripRequest,
    WeatherDay,
)


class PgRepo:
    """Repository cài đặt bằng PostgreSQL thuần qua psycopg2."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or config.DATABASE_URL

    def _get_conn(self):
        if psycopg2 is None:
            raise RuntimeError(
                f"Không thể khởi tạo psycopg2 trên môi trường hiện tại: {_PSYCOPG2_ERROR}. "
                "Lưu ý: Driver này hoạt động bình thường trên môi trường Linux/Render."
            )
        return psycopg2.connect(self.db_url)

    # ---------------------------------------------------------
    # users & preferences
    # ---------------------------------------------------------
    def create_user(self, email: str, password_hash: str, full_name: str) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name, is_admin)
                    VALUES (%s, %s, %s, FALSE)
                    RETURNING id
                    """,
                    (email, password_hash, full_name),
                )
                return cur.fetchone()[0]

    def get_user_by_email(self, email: str) -> Optional[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, email, password_hash, full_name, is_admin
                    FROM users WHERE email = %s
                    """,
                    (email,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_user(self, user_id: int) -> Optional[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, email, password_hash, full_name, is_admin
                    FROM users WHERE id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def save_preferences(self, user_id: int, interests: tuple[str, ...], travel_style: str) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))
                for interest in interests:
                    cur.execute(
                        """
                        INSERT INTO user_preferences (user_id, preference_type, preference_value)
                        VALUES (%s, 'interest', %s)
                        """,
                        (user_id, interest),
                    )
                if travel_style:
                    cur.execute(
                        """
                        INSERT INTO user_preferences (user_id, preference_type, preference_value)
                        VALUES (%s, 'travel_style', %s)
                        """,
                        (user_id, travel_style),
                    )

    def get_preferences(self, user_id: int) -> dict:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT preference_type, preference_value
                    FROM user_preferences WHERE user_id = %s
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                interests = [r[1] for r in rows if r[0] == "interest"]
                travel_style = next((r[1] for r in rows if r[0] == "travel_style"), None)
                return {"interests": interests, "travel_style": travel_style}

    # ---------------------------------------------------------
    # destinations & categories
    # ---------------------------------------------------------
    def _row_to_destination(self, row: dict) -> Destination:
        tags = row.get("tags") or []
        if isinstance(tags, str):
            tags = json.loads(tags)
        opening = row.get("opening_hours")
        if isinstance(opening, str):
            opening = json.loads(opening)

        return Destination(
            id=row["id"],
            name=row["name"],
            province=row["province"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            category_id=row.get("category_id") or 0,
            price_range=int(row["price_range"]),
            noise_level=int(row["noise_level"]),
            duration_hours=float(row["duration_hours"]),
            is_outdoor=bool(row["is_outdoor"]),
            tags=tuple(tags),
            opening_hours=opening,
            address=row.get("address") or "",
            description=row.get("description") or "",
            image_url=row.get("image_url") or "",
            avg_rating=float(row["avg_rating"]) if row.get("avg_rating") is not None else None,
        )

    def list_destinations(self, province: Optional[str] = None) -> list[Destination]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if province:
                    cur.execute(
                        """
                        SELECT id, name, province, address, latitude, longitude,
                               description, image_url, category_id, price_range,
                               noise_level, duration_hours, is_outdoor, opening_hours,
                               tags, avg_rating
                        FROM destinations WHERE province = %s
                        ORDER BY id ASC
                        """,
                        (province,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, name, province, address, latitude, longitude,
                               description, image_url, category_id, price_range,
                               noise_level, duration_hours, is_outdoor, opening_hours,
                               tags, avg_rating
                        FROM destinations
                        ORDER BY id ASC
                        """
                    )
                return [self._row_to_destination(r) for r in cur.fetchall()]

    def get_destination(self, destination_id: int) -> Optional[Destination]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, name, province, address, latitude, longitude,
                           description, image_url, category_id, price_range,
                           noise_level, duration_hours, is_outdoor, opening_hours,
                           tags, avg_rating
                    FROM destinations WHERE id = %s
                    """,
                    (destination_id,),
                )
                row = cur.fetchone()
                return self._row_to_destination(row) if row else None

    def save_destination(self, data: dict, destination_id: Optional[int] = None) -> int:
        opening = data.get("opening_hours")
        opening_json = json.dumps(opening) if opening is not None else None
        tags = data.get("tags") or []
        tags_json = json.dumps(list(tags))

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                if destination_id:
                    cur.execute(
                        """
                        UPDATE destinations
                        SET name = %s, province = %s, address = %s, latitude = %s, longitude = %s,
                            description = %s, image_url = %s, category_id = %s, price_range = %s,
                            noise_level = %s, duration_hours = %s, is_outdoor = %s,
                            opening_hours = %s, tags = %s
                        WHERE id = %s
                        """,
                        (
                            data["name"],
                            data["province"],
                            data.get("address", ""),
                            float(data["latitude"]),
                            float(data["longitude"]),
                            data.get("description", ""),
                            data.get("image_url", ""),
                            data.get("category_id"),
                            int(data["price_range"]),
                            int(data["noise_level"]),
                            float(data["duration_hours"]),
                            bool(data.get("is_outdoor", True)),
                            opening_json,
                            tags_json,
                            destination_id,
                        ),
                    )
                    return destination_id
                else:
                    cur.execute(
                        """
                        INSERT INTO destinations (
                            name, province, address, latitude, longitude,
                            description, image_url, category_id, price_range,
                            noise_level, duration_hours, is_outdoor, opening_hours, tags
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        ) RETURNING id
                        """,
                        (
                            data["name"],
                            data["province"],
                            data.get("address", ""),
                            float(data["latitude"]),
                            float(data["longitude"]),
                            data.get("description", ""),
                            data.get("image_url", ""),
                            data.get("category_id"),
                            int(data["price_range"]),
                            int(data["noise_level"]),
                            float(data["duration_hours"]),
                            bool(data.get("is_outdoor", True)),
                            opening_json,
                            tags_json,
                        ),
                    )
                    return cur.fetchone()[0]

    def delete_destination(self, destination_id: int) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM destinations WHERE id = %s", (destination_id,))

    def list_categories(self) -> list[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name, icon FROM categories ORDER BY id ASC")
                return [dict(r) for r in cur.fetchall()]

    def save_category(self, name: str, icon: str, category_id: Optional[int] = None) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                if category_id:
                    cur.execute(
                        "UPDATE categories SET name = %s, icon = %s WHERE id = %s",
                        (name, icon, category_id),
                    )
                    return category_id
                else:
                    cur.execute(
                        "INSERT INTO categories (name, icon) VALUES (%s, %s) RETURNING id",
                        (name, icon),
                    )
                    return cur.fetchone()[0]

    def delete_category(self, category_id: int) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM categories WHERE id = %s", (category_id,))

    # ---------------------------------------------------------
    # trips & itinerary items
    # ---------------------------------------------------------
    def save_trip(self, user_id: int, title: str, plan: TripPlan) -> int:
        req = plan.request
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trips (
                        user_id, title, destination_province, start_date, end_date,
                        total_days, budget, num_people, travel_style, status, is_public
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, 'draft', FALSE
                    ) RETURNING id
                    """,
                    (
                        user_id,
                        title,
                        req.province,
                        req.start_date,
                        req.start_date + timedelta(days=req.days - 1),
                        req.days,
                        req.budget,
                        req.num_people,
                        req.travel_style,
                    ),
                )
                trip_id = cur.fetchone()[0]

                for day in plan.days:
                    for item in day.items:
                        cur.execute(
                            """
                            INSERT INTO itinerary_items (
                                trip_id, destination_id, day_number, time_slot,
                                order_in_slot, estimated_cost, notes
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                trip_id,
                                item.destination.id,
                                item.day_number,
                                item.time_slot,
                                item.order_in_slot,
                                item.estimated_cost,
                                item.notes,
                            ),
                        )
                return trip_id

    def get_trip(self, trip_id: int) -> Optional[TripRecord]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, user_id, title, destination_province, start_date,
                           total_days, budget, num_people, travel_style, status,
                           is_public, share_token
                    FROM trips WHERE id = %s
                    """,
                    (trip_id,),
                )
                trip_row = cur.fetchone()
                if not trip_row:
                    return None

                # Lấy items
                cur.execute(
                    """
                    SELECT i.id, i.trip_id, i.destination_id, i.day_number, i.time_slot,
                           i.order_in_slot, i.estimated_cost, i.notes,
                           d.id as d_id, d.name, d.province, d.address, d.latitude, d.longitude,
                           d.description, d.image_url, d.category_id, d.price_range,
                           d.noise_level, d.duration_hours, d.is_outdoor, d.opening_hours,
                           d.tags, d.avg_rating
                    FROM itinerary_items i
                    JOIN destinations d ON i.destination_id = d.id
                    WHERE i.trip_id = %s
                    ORDER BY i.day_number ASC, i.time_slot ASC, i.order_in_slot ASC
                    """,
                    (trip_id,),
                )
                item_rows = cur.fetchall()

                # Tái cấu trúc TripPlan
                days_dict = {}
                for r in item_rows:
                    dest = self._row_to_destination({
                        "id": r["d_id"],
                        "name": r["name"],
                        "province": r["province"],
                        "address": r["address"],
                        "latitude": r["latitude"],
                        "longitude": r["longitude"],
                        "description": r["description"],
                        "image_url": r["image_url"],
                        "category_id": r["category_id"],
                        "price_range": r["price_range"],
                        "noise_level": r["noise_level"],
                        "duration_hours": r["duration_hours"],
                        "is_outdoor": r["is_outdoor"],
                        "opening_hours": r["opening_hours"],
                        "tags": r["tags"],
                        "avg_rating": r["avg_rating"],
                    })
                    item = ItineraryItem(
                        destination=dest,
                        day_number=r["day_number"],
                        time_slot=r["time_slot"],
                        order_in_slot=r["order_in_slot"],
                        estimated_cost=r["estimated_cost"],
                        notes=r["notes"],
                        id=r["id"],
                    )
                    days_dict.setdefault(r["day_number"], []).append(item)

                total_days = trip_row["total_days"]
                start_date = trip_row["start_date"]
                day_plans = []
                for d_num in range(1, total_days + 1):
                    d_date = start_date + timedelta(days=d_num - 1)
                    items_tuple = tuple(days_dict.get(d_num, []))
                    day_plans.append(DayPlan(day_number=d_num, date=d_date, items=items_tuple, weather=None))

                # Lấy sở thích user
                cur.execute(
                    "SELECT preference_value FROM user_preferences WHERE user_id = %s AND preference_type = 'interest'",
                    (trip_row["user_id"],),
                )
                user_interests = tuple(r["preference_value"] for r in cur.fetchall()) or ("thien_nhien",)

                req = TripRequest(
                    province=trip_row["destination_province"],
                    start_date=start_date,
                    days=total_days,
                    budget=trip_row["budget"],
                    num_people=trip_row["num_people"],
                    interests=user_interests,
                    travel_style=trip_row["travel_style"],
                    user_id=trip_row["user_id"],
                )

                # Cost Breakdown tính nhanh
                from app.contracts import BUDGET_SPLIT
                b = trip_row["budget"]
                alloc = {k: round(b * BUDGET_SPLIT[k]) for k in ("luu_tru", "an_uong", "di_chuyen", "ve_vao_cua")}
                alloc["du_phong"] = b - sum(alloc.values())
                t_est = sum(i["estimated_cost"] for i in item_rows)
                cost = CostBreakdown(
                    budget=b,
                    per_day=b // total_days,
                    allocation=alloc,
                    tickets_estimated=t_est,
                    within_budget=t_est <= alloc["ve_vao_cua"],
                )

                plan = TripPlan(request=req, days=tuple(day_plans), cost=cost, warnings=())
                return TripRecord(
                    id=trip_row["id"],
                    user_id=trip_row["user_id"],
                    title=trip_row["title"],
                    status=trip_row["status"],
                    is_public=trip_row["is_public"],
                    share_token=trip_row["share_token"],
                    plan=plan,
                )

    def get_trip_by_token(self, token: str) -> Optional[TripRecord]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM trips WHERE share_token = %s AND is_public = TRUE", (token,))
                row = cur.fetchone()
                if not row:
                    return None
                return self.get_trip(row[0])

    def list_trips(self, user_id: int) -> list[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, title, destination_province as province, start_date, total_days as days, status
                    FROM trips WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                )
                return [dict(r) for r in cur.fetchall()]

    def delete_trip(self, trip_id: int) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM trips WHERE id = %s", (trip_id,))

    def add_item(
        self, trip_id: int, destination_id: int, day_number: int,
        time_slot: str, order_in_slot: int, estimated_cost: int
    ) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO itinerary_items (
                        trip_id, destination_id, day_number, time_slot, order_in_slot, estimated_cost
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (trip_id, destination_id, day_number, time_slot, order_in_slot, estimated_cost),
                )
                return cur.fetchone()[0]

    def update_item(self, item_id: int, **fields) -> None:
        valid_cols = {"day_number", "time_slot", "order_in_slot", "destination_id", "estimated_cost", "notes"}
        updates = {k: v for k, v in fields.items() if k in valid_cols and v is not None}
        if not updates:
            return

        set_clause = ", ".join(f"{col} = %s" for col in updates)
        values = list(updates.values())
        values.append(item_id)

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE itinerary_items SET {set_clause} WHERE id = %s", tuple(values))

    def delete_item(self, item_id: int) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM itinerary_items WHERE id = %s", (item_id,))

    def set_sharing(self, trip_id: int, is_public: bool) -> Optional[str]:
        import secrets
        token = secrets.token_urlsafe(16) if is_public else None
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE trips SET is_public = %s, share_token = %s WHERE id = %s",
                    (is_public, token, trip_id),
                )
        return token

    def set_status(self, trip_id: int, status: str) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE trips SET status = %s WHERE id = %s", (status, trip_id))

    # ---------------------------------------------------------
    # ratings
    # ---------------------------------------------------------
    def save_rating(self, user_id: int, destination_id: int, trip_id: int, score: int, review_text: str) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ratings (user_id, destination_id, trip_id, score, review_text, is_approved)
                    VALUES (%s, %s, %s, %s, %s, FALSE)
                    RETURNING id
                    """,
                    (user_id, destination_id, trip_id, score, review_text),
                )
                return cur.fetchone()[0]

    def list_approved_ratings(self) -> list[tuple[int, int, int]]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, destination_id, score FROM ratings WHERE is_approved = TRUE ORDER BY id ASC"
                )
                return cur.fetchall()

    def list_pending_ratings(self) -> list[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT r.id, r.user_id, r.destination_id, r.trip_id, r.score, r.review_text,
                           r.created_at, u.full_name as user_name, d.name as destination_name
                    FROM ratings r
                    JOIN users u ON r.user_id = u.id
                    JOIN destinations d ON r.destination_id = d.id
                    WHERE r.is_approved = FALSE
                    ORDER BY r.created_at DESC
                    """
                )
                return [dict(r) for r in cur.fetchall()]

    def set_rating_approved(self, rating_id: int, approved: bool) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ratings SET is_approved = %s WHERE id = %s RETURNING destination_id",
                    (approved, rating_id),
                )
                row = cur.fetchone()
                if row:
                    dest_id = row[0]
                    # Đồng thời cập nhật avg_rating
                    cur.execute(
                        """
                        UPDATE destinations
                        SET avg_rating = (
                            SELECT ROUND(AVG(score)::numeric, 1)
                            FROM ratings
                            WHERE destination_id = %s AND is_approved = TRUE
                        ) WHERE id = %s
                        """,
                        (dest_id, dest_id),
                    )

    # ---------------------------------------------------------
    # weather cache
    # ---------------------------------------------------------
    def get_weather_cache(self, province: str) -> Optional[tuple[dict, datetime]]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT weather_data, cached_at FROM weather_cache WHERE province = %s",
                    (province,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                data, cached_at = row
                if isinstance(data, str):
                    data = json.loads(data)
                return (data, cached_at)

    def put_weather_cache(self, province: str, raw: dict) -> None:
        raw_json = json.dumps(raw)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO weather_cache (province, weather_data, cached_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (province) DO UPDATE
                    SET weather_data = EXCLUDED.weather_data, cached_at = CURRENT_TIMESTAMP
                    """,
                    (province, raw_json),
                )

    # ---------------------------------------------------------
    # admin
    # ---------------------------------------------------------
    def admin_stats(self) -> dict:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # top destinations
                cur.execute(
                    """
                    SELECT d.name, COUNT(r.id) as count
                    FROM destinations d
                    LEFT JOIN ratings r ON d.id = r.destination_id
                    GROUP BY d.id, d.name
                    ORDER BY count DESC
                    LIMIT 5
                    """
                )
                top_dest = [dict(r) for r in cur.fetchall()]

                # top provinces
                cur.execute(
                    """
                    SELECT destination_province as province, COUNT(id) as count
                    FROM trips
                    GROUP BY destination_province
                    ORDER BY count DESC
                    """
                )
                top_prov = [dict(r) for r in cur.fetchall()]

                # totals
                cur.execute("SELECT COUNT(*) FROM users")
                u_cnt = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) FROM destinations")
                d_cnt = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) FROM trips")
                t_cnt = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) FROM ratings")
                r_cnt = cur.fetchone()["count"]

                return {
                    "top_destinations": top_dest,
                    "top_provinces": top_prov,
                    "totals": {"users": u_cnt, "destinations": d_cnt, "trips": t_cnt, "ratings": r_cnt},
                }
