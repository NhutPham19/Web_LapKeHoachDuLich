from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app.auth import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/stats")
@admin_required
def stats_view():
    stats = current_app.repo.admin_stats()
    return render_template("admin/stats.html", stats=stats)


@admin_bp.route("/destinations")
@admin_required
def destinations_view():
    dests = current_app.repo.list_destinations()
    return render_template("admin/destinations.html", destinations=dests)


@admin_bp.route("/destinations/new", methods=["GET", "POST"])
@admin_required
def new_destination():
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "province": request.form.get("province", "").strip(),
            "address": request.form.get("address", "").strip(),
            "latitude": float(request.form.get("latitude", 0)),
            "longitude": float(request.form.get("longitude", 0)),
            "description": request.form.get("description", "").strip(),
            "image_url": request.form.get("image_url", "").strip(),
            "price_range": int(request.form.get("price_range", 1)),
            "noise_level": int(request.form.get("noise_level", 3)),
            "duration_hours": float(request.form.get("duration_hours", 1.0)),
            "is_outdoor": request.form.get("is_outdoor") == "1",
            "tags": tuple(request.form.getlist("tags")),
            "opening_hours": None,
        }
        current_app.repo.save_destination(data)
        flash("Đã thêm địa điểm thành công!", "success")
        return redirect(url_for("admin.destinations_view"))

    categories = current_app.repo.list_categories()
    return render_template("admin/destination_form.html", destination=None, categories=categories)


@admin_bp.route("/destinations/<int:dest_id>/edit", methods=["GET"])
@admin_required
def edit_destination_view(dest_id: int):
    dest = current_app.repo.get_destination(dest_id)
    if not dest:
        flash("Không tìm thấy địa điểm", "danger")
        return redirect(url_for("admin.destinations_view"))
    categories = current_app.repo.list_categories()
    return render_template("admin/destination_form.html", destination=dest, categories=categories)


@admin_bp.route("/destinations/<int:dest_id>", methods=["POST"])
@admin_required
def update_destination(dest_id: int):
    data = {
        "name": request.form.get("name", "").strip(),
        "province": request.form.get("province", "").strip(),
        "address": request.form.get("address", "").strip(),
        "latitude": float(request.form.get("latitude", 0)),
        "longitude": float(request.form.get("longitude", 0)),
        "description": request.form.get("description", "").strip(),
        "image_url": request.form.get("image_url", "").strip(),
        "price_range": int(request.form.get("price_range", 1)),
        "noise_level": int(request.form.get("noise_level", 3)),
        "duration_hours": float(request.form.get("duration_hours", 1.0)),
        "is_outdoor": request.form.get("is_outdoor") == "1",
        "tags": tuple(request.form.getlist("tags")),
        "opening_hours": None,
    }
    current_app.repo.save_destination(data, destination_id=dest_id)
    flash("Đã cập nhật địa điểm thành công!", "success")
    return redirect(url_for("admin.destinations_view"))


@admin_bp.route("/destinations/<int:dest_id>/delete", methods=["POST"])
@admin_required
def delete_destination(dest_id: int):
    current_app.repo.delete_destination(dest_id)
    flash("Đã xóa địa điểm.", "info")
    return redirect(url_for("admin.destinations_view"))


@admin_bp.route("/ratings", methods=["GET", "POST"])
@admin_required
def ratings_view():
    if request.method == "POST":
        rating_id = int(request.form.get("rating_id"))
        approved = request.form.get("action") == "approve"
        current_app.repo.set_rating_approved(rating_id, approved)
        flash(f"Đã {'duyệt' if approved else 'từ chối'} đánh giá #{rating_id}.", "success")
        return redirect(url_for("admin.ratings_view"))

    pending = current_app.repo.list_pending_ratings()
    return render_template("admin/ratings.html", pending_ratings=pending)


@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories_view():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        icon = request.form.get("icon", "").strip()
        if name:
            current_app.repo.save_category(name, icon)
            flash("Đã thêm danh mục thành công!", "success")
        return redirect(url_for("admin.categories_view"))

    cats = current_app.repo.list_categories()
    return render_template("admin/categories.html", categories=cats)
