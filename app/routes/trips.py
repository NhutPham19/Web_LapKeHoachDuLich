from datetime import date
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.auth import login_required
from app.contracts import (
    INTERESTS,
    PROVINCES,
    TRAVEL_STYLES,
    TripRequest,
)
from app.services import planner, weather

trips_bp = Blueprint("trips", __name__)


@trips_bp.route("/trips")
@login_required
def list_trips_view():
    user_id = session["user"]["id"]
    user_trips = current_app.repo.list_trips(user_id)
    return render_template("trips.html", trips=user_trips)


@trips_bp.route("/trips/new", methods=["GET", "POST"])
@login_required
def new_trip_view():
    user_id = session["user"]["id"]
    if request.method == "POST":
        province = request.form.get("province", "").strip()
        start_date_str = request.form.get("start_date", "").strip()
        days_str = request.form.get("days", "").strip()
        budget_str = request.form.get("budget", "").strip()
        num_people_str = request.form.get("num_people", "").strip()
        interests = tuple(dict.fromkeys(request.form.getlist("interests")))
        travel_style = request.form.get("travel_style", "").strip()

        # Validate theo 1.G.7
        if province not in PROVINCES:
            flash("Tỉnh/thành phố điểm đến không hợp lệ.", "danger")
            return redirect(url_for("trips.new_trip_view"))

        try:
            start_date = date.fromisoformat(start_date_str)
            if start_date < date.today():
                flash("Ngày bắt đầu không được nằm trong quá khứ.", "danger")
                return redirect(url_for("trips.new_trip_view"))
        except Exception:
            flash("Định dạng ngày bắt đầu không hợp lệ.", "danger")
            return redirect(url_for("trips.new_trip_view"))

        try:
            days = int(days_str)
            if not (1 <= days <= 7):
                flash("Số ngày đi phải từ 1 đến 7 ngày.", "danger")
                return redirect(url_for("trips.new_trip_view"))
        except Exception:
            flash("Số ngày đi không hợp lệ.", "danger")
            return redirect(url_for("trips.new_trip_view"))

        try:
            budget = int(budget_str)
            if budget < 100_000:
                flash("Tổng ngân sách tối thiểu là 100,000 VNĐ.", "danger")
                return redirect(url_for("trips.new_trip_view"))
        except Exception:
            flash("Số tiền ngân sách không hợp lệ.", "danger")
            return redirect(url_for("trips.new_trip_view"))

        try:
            num_people = int(num_people_str)
            if not (1 <= num_people <= 20):
                flash("Số lượng người đi phải từ 1 đến 20 người.", "danger")
                return redirect(url_for("trips.new_trip_view"))
        except Exception:
            flash("Số lượng người không hợp lệ.", "danger")
            return redirect(url_for("trips.new_trip_view"))

        if not interests or not set(interests).issubset(INTERESTS):
            flash("Vui lòng chọn ít nhất 1 sở thích hợp lệ.", "danger")
            return redirect(url_for("trips.new_trip_view"))

        if travel_style not in TRAVEL_STYLES:
            flash("Phong cách du lịch không hợp lệ.", "danger")
            return redirect(url_for("trips.new_trip_view"))

        # Dựng TripRequest
        trip_req = TripRequest(
            province=province,
            start_date=start_date,
            days=days,
            budget=budget,
            num_people=num_people,
            interests=interests,
            travel_style=travel_style,
            user_id=user_id,
        )

        # Lấy dữ liệu từ repo
        all_dests = current_app.repo.list_destinations()
        approved_ratings = current_app.repo.list_approved_ratings()

        # Lấy thời tiết an toàn
        try:
            w_forecast = weather.get_forecast(
                province,
                start_date,
                days,
                cache_get=current_app.repo.get_weather_cache,
                cache_put=current_app.repo.put_weather_cache,
            )
        except Exception:
            w_forecast = []

        # Tạo kế hoạch thông minh
        plan = planner.generate_plan(trip_req, all_dests, approved_ratings, w_forecast)

        title = f"Kế hoạch {province} {days}N ({start_date.strftime('%d/%m/%Y')})"
        trip_id = current_app.repo.save_trip(user_id, title, plan)

        flash("Đã tạo kế hoạch du lịch cá nhân hóa thành công!", "success")
        return redirect(f"/trips/{trip_id}")

    prefs = current_app.repo.get_preferences(user_id)
    return render_template(
        "trip_new.html",
        pref_interests=prefs.get("interests", []),
        pref_style=prefs.get("travel_style", "thoai_mai"),
    )


@trips_bp.route("/trips/<int:trip_id>")
@login_required
def trip_detail_view(trip_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        abort(404)
    if trip.user_id != session["user"]["id"]:
        abort(403)
    return render_template("trip_detail.html", trip=trip, is_owner=True)


@trips_bp.route("/trips/<int:trip_id>/delete", methods=["POST"])
@login_required
def delete_trip_view(trip_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        abort(404)
    if trip.user_id != session["user"]["id"]:
        abort(403)
    current_app.repo.delete_trip(trip_id)
    flash("Đã xóa kế hoạch chuyến đi.", "info")
    return redirect(url_for("trips.list_trips_view"))


# -------------------------------------------------------------
# API Items
# -------------------------------------------------------------
@trips_bp.route("/api/trips/<int:trip_id>/items", methods=["POST"])
@login_required
def api_add_item(trip_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        return {"error": "not_found", "message": "Chuyến đi không tồn tại"}, 404
    if trip.user_id != session["user"]["id"]:
        return {"error": "forbidden", "message": "Bạn không có quyền chỉnh sửa"}, 403

    data = request.get_json() or {}
    dest_id = data.get("destination_id")
    day_num = data.get("day_number", 1)
    slot = data.get("time_slot", "morning")

    dest = current_app.repo.get_destination(dest_id)
    if not dest:
        return {"error": "bad_request", "message": "Địa điểm không tồn tại"}, 400

    from app.contracts import TICKET_PRICE_BY_RANGE
    est_cost = TICKET_PRICE_BY_RANGE.get(dest.price_range, 0) * trip.plan.request.num_people

    new_id = current_app.repo.add_item(trip_id, dest_id, day_num, slot, 1, est_cost)
    return jsonify({"id": new_id}), 201


@trips_bp.route("/api/trips/<int:trip_id>/items/<int:item_id>", methods=["PATCH"])
@login_required
def api_update_item(trip_id: int, item_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        return {"error": "not_found", "message": "Chuyến đi không tồn tại"}, 404
    if trip.user_id != session["user"]["id"]:
        return {"error": "forbidden", "message": "Bạn không có quyền chỉnh sửa"}, 403

    data = request.get_json() or {}
    current_app.repo.update_item(item_id, **data)
    return jsonify({"ok": True}), 200


@trips_bp.route("/api/trips/<int:trip_id>/items/<int:item_id>", methods=["DELETE"])
@login_required
def api_delete_item(trip_id: int, item_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        return {"error": "not_found", "message": "Chuyến đi không tồn tại"}, 404
    if trip.user_id != session["user"]["id"]:
        return {"error": "forbidden", "message": "Bạn không có quyền chỉnh sửa"}, 403

    current_app.repo.delete_item(item_id)
    return jsonify({"ok": True}), 200


# -------------------------------------------------------------
# Chia sẻ & Trạng thái
# -------------------------------------------------------------
@trips_bp.route("/api/trips/<int:trip_id>/share", methods=["POST"])
@login_required
def api_share_trip(trip_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        return {"error": "not_found", "message": "Chuyến đi không tồn tại"}, 404
    if trip.user_id != session["user"]["id"]:
        return {"error": "forbidden", "message": "Bạn không có quyền chia sẻ"}, 403

    data = request.get_json() or {}
    is_public = bool(data.get("is_public", False))
    token = current_app.repo.set_sharing(trip_id, is_public)

    share_url = f"{request.host_url}s/{token}" if token else None
    return jsonify({"is_public": is_public, "share_url": share_url})


@trips_bp.route("/s/<share_token>")
def public_shared_trip_view(share_token: str):
    trip = current_app.repo.get_trip_by_token(share_token)
    if not trip:
        abort(404)
    return render_template("trip_detail.html", trip=trip, is_owner=False)


@trips_bp.route("/api/trips/<int:trip_id>/complete", methods=["POST"])
@login_required
def api_complete_trip(trip_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        return {"error": "not_found", "message": "Chuyến đi không tồn tại"}, 404
    if trip.user_id != session["user"]["id"]:
        return {"error": "forbidden", "message": "Bạn không có quyền chỉnh sửa"}, 403

    current_app.repo.set_status(trip_id, "completed")
    return redirect(f"/trips/{trip_id}")
