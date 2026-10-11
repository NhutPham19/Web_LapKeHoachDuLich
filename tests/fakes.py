from dataclasses import replace
from datetime import datetime

from app.contracts import DayPlan, Destination, ItineraryItem, TripPlan, TripRecord


class FakeRepo:
    """Repository in-memory dành riêng cho test; không gọi DB hoặc mạng."""

    def __init__(self, destinations=()):
        self.users = {}
        self.preferences = {}
        self.destinations = {destination.id: destination for destination in destinations}
        self.categories = {}
        self.trips = {}
        self.items = {}
        self.ratings = {}
        self.weather_cache = {}
        self._next_ids = {"user": 1, "destination": max(self.destinations, default=0) + 1,
                          "category": 1, "trip": 1, "item": 1, "rating": 1}

    def _next(self, kind):
        value = self._next_ids[kind]
        self._next_ids[kind] += 1
        return value

    def create_user(self, email, password_hash, full_name):
        user_id = self._next("user")
        self.users[user_id] = {"id": user_id, "email": email, "password_hash": password_hash,
                               "full_name": full_name, "is_admin": False}
        return user_id

    def get_user_by_email(self, email):
        return next((dict(user) for user in self.users.values() if user["email"] == email), None)

    def get_user(self, user_id):
        user = self.users.get(user_id)
        return dict(user) if user else None

    def set_user_admin(self, email, is_admin=True):
        user = self.get_user_by_email(email)
        if user:
            self.users[user["id"]]["is_admin"] = is_admin
            return True
        return False

    def ping_db(self):
        return True

    def save_preferences(self, user_id, interests, travel_style):
        self.preferences[user_id] = {"interests": list(interests), "travel_style": travel_style}

    def get_preferences(self, user_id):
        return dict(self.preferences.get(user_id, {"interests": [], "travel_style": None}))

    def list_destinations(self, province=None, active_only=True):
        return [destination for destination in self.destinations.values()
                if (province is None or destination.province == province)
                and (not active_only or getattr(destination, "is_active", True))]

    def get_destination(self, destination_id):
        return self.destinations.get(destination_id)

    def save_destination(self, data, destination_id=None):
        destination_id = destination_id or self._next("destination")
        values = dict(data)
        values.pop("id", None)
        values["tags"] = tuple(values["tags"])
        if "ticket_price" not in values:
            values["ticket_price"] = 0
        if "category_name" not in values:
            cat = self.categories.get(values.get("category_id"))
            values["category_name"] = cat["name"] if cat else ""
        if "is_active" not in values:
            values["is_active"] = True
        self.destinations[destination_id] = Destination(id=destination_id, **values)
        return destination_id

    def delete_destination(self, destination_id):
        dest = self.destinations.get(destination_id)
        if dest:
            self.destinations[destination_id] = replace(dest, is_active=False)

    def list_categories(self):
        return [dict(category) for category in self.categories.values()]

    def save_category(self, name, icon, category_id=None):
        category_id = category_id or self._next("category")
        self.categories[category_id] = {"id": category_id, "name": name, "icon": icon}
        return category_id

    def delete_category(self, category_id):
        has_active_dest = any(
            d.category_id == category_id and getattr(d, "is_active", True)
            for d in self.destinations.values()
        )
        if has_active_dest:
            return False
        self.categories.pop(category_id, None)
        return True

    def save_trip(self, user_id, title, plan):
        trip_id = self._next("trip")
        self.trips[trip_id] = TripRecord(trip_id, user_id, title, "draft", False, None, plan)
        for day in plan.days:
            for item in day.items:
                item_id = item.id or self._next("item")
                self._next_ids["item"] = max(self._next_ids["item"], item_id + 1)
                self.items[item_id] = {
                    "id": item_id,
                    "trip_id": trip_id,
                    "destination_id": item.destination.id,
                    "day_number": item.day_number,
                    "time_slot": item.time_slot,
                    "order_in_slot": item.order_in_slot,
                    "estimated_cost": item.estimated_cost,
                    "travel_km_from_prev": getattr(item, "travel_km_from_prev", 0.0),
                    "notes": item.notes,
                }
        self._sync_trip(trip_id)
        return trip_id

    def get_trip(self, trip_id):
        return self.trips.get(trip_id)

    def get_trip_by_token(self, token):
        return next((trip for trip in self.trips.values()
                     if trip.is_public and trip.share_token == token), None)

    def list_trips(self, user_id):
        return [{"id": trip.id, "title": trip.title, "province": trip.plan.request.province,
                 "start_date": trip.plan.request.start_date, "days": trip.plan.request.days,
                 "status": trip.status} for trip in self.trips.values() if trip.user_id == user_id]

    def delete_trip(self, trip_id):
        self.trips.pop(trip_id, None)
        self.items = {item_id: item for item_id, item in self.items.items() if item["trip_id"] != trip_id}

    def add_item(self, trip_id, destination_id, day_number, time_slot, order_in_slot, estimated_cost, travel_km_from_prev=0.0, notes=""):
        item_id = self._next("item")
        self.items[item_id] = {
            "id": item_id,
            "trip_id": trip_id,
            "destination_id": destination_id,
            "day_number": day_number,
            "time_slot": time_slot,
            "order_in_slot": order_in_slot,
            "estimated_cost": estimated_cost,
            "travel_km_from_prev": travel_km_from_prev,
            "notes": notes,
        }
        self._sync_trip(trip_id)
        return item_id

    def update_item(self, trip_id, item_id, fields):
        item = self.items.get(item_id)
        if item and item.get("trip_id") == trip_id:
            valid_cols = {"day_number", "time_slot", "order_in_slot", "destination_id", "estimated_cost", "travel_km_from_prev", "notes"}
            item.update({key: value for key, value in fields.items() if key in valid_cols and value is not None})
            self._sync_trip(trip_id)

    def delete_item(self, trip_id, item_id):
        item = self.items.get(item_id)
        if item and item.get("trip_id") == trip_id:
            del self.items[item_id]
            self._sync_trip(trip_id)

    def set_sharing(self, trip_id, is_public):
        trip = self.trips[trip_id]
        import secrets
        token = secrets.token_urlsafe(16) if is_public else None
        self.trips[trip_id] = replace(trip, is_public=is_public, share_token=token)
        return token

    def set_status(self, trip_id, status):
        self.trips[trip_id] = replace(self.trips[trip_id], status=status)

    def save_rating(self, user_id, destination_id, trip_id, score, review_text=""):
        key = (user_id, trip_id, destination_id)
        for r_id, r in self.ratings.items():
            if (r["user_id"], r["trip_id"], r["destination_id"]) == key:
                r["score"] = score
                r["review_text"] = review_text
                r["is_approved"] = False
                return r_id

        rating_id = self._next("rating")
        self.ratings[rating_id] = {
            "id": rating_id,
            "user_id": user_id,
            "destination_id": destination_id,
            "trip_id": trip_id,
            "score": score,
            "review_text": review_text,
            "is_approved": False,
        }
        return rating_id

    def list_approved_ratings(self):
        return [(rating["user_id"], rating["destination_id"], rating["score"])
                for rating in self.ratings.values() if rating["is_approved"]]

    def list_pending_ratings(self):
        return [dict(rating) for rating in self.ratings.values() if not rating["is_approved"]]

    def set_rating_approved(self, rating_id, approved):
        rating = self.ratings[rating_id]
        rating["is_approved"] = approved
        scores = [entry["score"] for entry in self.ratings.values()
                  if entry["destination_id"] == rating["destination_id"] and entry["is_approved"]]
        destination = self.destinations.get(rating["destination_id"])
        if destination:
            self.destinations[destination.id] = replace(destination,
                                                         avg_rating=sum(scores) / len(scores) if scores else None)

    def get_weather_cache(self, province):
        return self.weather_cache.get(province)

    def put_weather_cache(self, province, raw):
        self.weather_cache[province] = (raw, datetime.now())

    def admin_stats(self):
        counts = {}
        for rating in self.ratings.values():
            counts[rating["destination_id"]] = counts.get(rating["destination_id"], 0) + 1
        top_destinations = [{"name": self.destinations[destination_id].name, "count": count}
                            for destination_id, count in sorted(counts.items(), key=lambda pair: -pair[1])
                            if destination_id in self.destinations]
        province_counts = {}
        for trip in self.trips.values():
            province = trip.plan.request.province
            province_counts[province] = province_counts.get(province, 0) + 1
        return {"top_destinations": top_destinations,
                "top_provinces": [{"province": province, "count": count}
                                  for province, count in sorted(province_counts.items(), key=lambda pair: -pair[1])],
                "totals": {"users": len(self.users), "destinations": len(self.destinations),
                           "trips": len(self.trips), "ratings": len(self.ratings)}}

    def _sync_trip(self, trip_id):
        trip = self.trips.get(trip_id)
        if not trip:
            return
        by_day = {}
        for item in self.items.values():
            if item["trip_id"] == trip_id and item["destination_id"] in self.destinations:
                by_day.setdefault(item["day_number"], []).append(item)
        days = []
        for day in trip.plan.days:
            items = tuple(ItineraryItem(
                destination=self.destinations[item["destination_id"]],
                day_number=item["day_number"],
                time_slot=item["time_slot"],
                order_in_slot=item["order_in_slot"],
                estimated_cost=item["estimated_cost"],
                travel_km_from_prev=float(item.get("travel_km_from_prev") or 0.0),
                notes=item["notes"],
                id=item["id"],
            ) for item in sorted(by_day.get(day.day_number, []),
                                 key=lambda entry: (entry["time_slot"], entry["order_in_slot"])))
            days.append(DayPlan(day.day_number, day.date, items, day.weather))
        self.trips[trip_id] = replace(trip, plan=replace(trip.plan, days=tuple(days)))
