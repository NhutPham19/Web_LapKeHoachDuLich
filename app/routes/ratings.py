from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session

from app.auth import login_required

ratings_bp = Blueprint("ratings", __name__)


@ratings_bp.route("/trips/<int:trip_id>/rate", methods=["GET", "POST"])
@login_required
def rate_trip_view(trip_id: int):
    trip = current_app.repo.get_trip(trip_id)
    if not trip:
        abort(404)
    user_id = session["user"]["id"]
    if trip.user_id != user_id:
        abort(403)
    if trip.status != "completed":
        flash("Chỉ có thể đánh giá sau khi chuyến đi đã hoàn thành.", "warning")
        return redirect(f"/trips/{trip_id}")

    # Lấy danh sách địa điểm duy nhất trong trip
    dests = {}
    for day in trip.plan.days:
        for item in day.items:
            dests[item.destination.id] = item.destination

    if request.method == "POST":
        for d_id in dests:
            score_str = request.form.get(f"score_{d_id}")
            review_text = request.form.get(f"review_{d_id}", "").strip()
            if score_str:
                try:
                    score_val = int(score_str)
                    if 1 <= score_val <= 5:
                        current_app.repo.save_rating(
                            user_id=user_id,
                            destination_id=d_id,
                            trip_id=trip_id,
                            score=score_val,
                            review_text=review_text,
                        )
                except Exception:
                    pass

        flash("Cảm ơn bạn đã gửi đánh giá! Đánh giá sẽ được hiển thị sau khi duyệt.", "success")
        return redirect(f"/trips/{trip_id}")

    return render_template("rate.html", trip=trip, destinations=list(dests.values()))
