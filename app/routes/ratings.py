from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session

from app.auth import login_required
from app.routes.trips import today_vn

ratings_bp = Blueprint("ratings", __name__)


@ratings_bp.route("/trips/<int:trip_id>/rate", methods=["GET", "POST"])
@login_required
def rate_trip_view(trip_id: int):
    trip = current_app.repo.get_trip(trip_id)
    user_id = session["user"]["id"]
    # Finding #9: trả 404 nếu không phải chủ
    if not trip or trip.user_id != user_id:
        abort(404)

    # Finding #4: kiểm tra ngày đi và trạng thái completed
    if today_vn() < trip.plan.request.start_date or trip.status != "completed":
        flash("Chỉ có thể đánh giá sau khi chuyến đi đã hoàn thành.", "warning")
        return redirect(f"/trips/{trip_id}")

    # Lấy danh sách địa điểm duy nhất thuộc chính trip này
    dests = {}
    for day in trip.plan.days:
        for item in day.items:
            dests[item.destination.id] = item.destination

    if request.method == "POST":
        for d_id in dests:
            score_str = request.form.get(f"score_{d_id}")
            review_text = request.form.get(f"review_{d_id}", "").strip()
            # Finding #4: trần độ dài 1000 ký tự
            if len(review_text) > 1000:
                review_text = review_text[:1000]

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

        flash("Cảm ơn bạn đã gửi đánh giá! Đánh giá sẽ được hiển thị sau khi quản trị viên phê duyệt.", "success")
        return redirect(f"/trips/{trip_id}")

    return render_template("rate.html", trip=trip, destinations=list(dests.values()))

