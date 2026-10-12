from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app.auth import admin_required
from app.contracts import PROVINCES
from app.services.cloudinary_uploader import upload_image_file

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/stats")
@admin_required
def stats_view():
    stats = current_app.repo.admin_stats()
    return render_template("admin/stats.html", stats=stats)


@admin_bp.route("/destinations")
@admin_required
def destinations_view():
    q = request.args.get("q", "").strip()
    province = request.args.get("province", "").strip()
    category_id = request.args.get("category_id", "").strip()
    is_outdoor = request.args.get("is_outdoor", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 15

    if page < 1:
        page = 1

    dests = current_app.repo.list_destinations(active_only=False)

    # Lọc danh sách
    filtered = []
    q_lower = q.lower()
    for d in dests:
        if q_lower:
            match_name = q_lower in d.name.lower()
            match_addr = q_lower in (d.address or "").lower()
            match_tags = any(q_lower in tag.lower() for tag in (d.tags or ()))
            if not (match_name or match_addr or match_tags):
                continue

        if province and d.province != province:
            continue

        if category_id:
            try:
                cid = int(category_id)
                if d.category_id != cid:
                    continue
            except ValueError:
                pass

        if is_outdoor != "":
            if is_outdoor == "1" and not d.is_outdoor:
                continue
            if is_outdoor == "0" and d.is_outdoor:
                continue

        filtered.append(d)

    total_count = len(filtered)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_dests = filtered[start_idx:end_idx]

    categories = current_app.repo.list_categories()

    return render_template(
        "admin/destinations.html",
        destinations=paginated_dests,
        categories=categories,
        provinces=PROVINCES,
        current_page=page,
        total_pages=total_pages,
        total_count=total_count,
        per_page=per_page,
        filters={
            "q": q,
            "province": province,
            "category_id": category_id,
            "is_outdoor": is_outdoor,
        },
    )


@admin_bp.route("/destinations/new", methods=["GET", "POST"])
@admin_required
def new_destination():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        province = request.form.get("province", "").strip()
        img = request.form.get("image_url", "").strip()
        if img and not (img.startswith("http://") or img.startswith("https://")):
            img = ""

        # Upload file ảnh từ máy nếu có
        image_file = request.files.get("image_file")
        image_public_id = None
        image_source = "manual"
        if image_file and image_file.filename:
            try:
                upload_res = upload_image_file(image_file, province, name)
                if upload_res:
                    image_public_id = upload_res["public_id"]
                    img = upload_res["secure_url"]
                    image_source = "admin_upload"
                    flash("Đã tải ảnh lên Cloudinary thành công!", "success")
            except Exception as e:
                flash(f"Lỗi tải ảnh lên Cloudinary ({e}), lưu thông tin không kèm ảnh mới.", "warning")

        data = {
            "name": name,
            "province": province,
            "address": request.form.get("address", "").strip(),
            "latitude": float(request.form.get("latitude", 0)),
            "longitude": float(request.form.get("longitude", 0)),
            "description": request.form.get("description", "").strip(),
            "image_url": img,
            "image_public_id": image_public_id,
            "image_source": image_source,
            "category_id": int(request.form.get("category_id")) if request.form.get("category_id") else None,
            "price_range": int(request.form.get("price_range", 1)),
            "noise_level": int(request.form.get("noise_level", 3)),
            "duration_hours": float(request.form.get("duration_hours", 1.0)),
            "is_outdoor": request.form.get("is_outdoor") == "1",
            "ticket_price": int(request.form.get("ticket_price", 0)),
            "is_active": True,
            "tags": tuple(request.form.getlist("tags")),
            "opening_hours": None,
        }
        current_app.repo.save_destination(data)
        flash("Đã thêm địa điểm thành công!", "success")
        return redirect(url_for("admin.destinations_view"))

    categories = current_app.repo.list_categories()
    return render_template("admin/destination_form.html", destination=None, categories=categories, provinces=PROVINCES)


@admin_bp.route("/destinations/<int:dest_id>/edit", methods=["GET"])
@admin_required
def edit_destination_view(dest_id: int):
    dest = current_app.repo.get_destination(dest_id)
    if not dest:
        flash("Không tìm thấy địa điểm", "danger")
        return redirect(url_for("admin.destinations_view"))
    categories = current_app.repo.list_categories()
    return render_template("admin/destination_form.html", destination=dest, categories=categories, provinces=PROVINCES)


@admin_bp.route("/destinations/<int:dest_id>", methods=["POST"])
@admin_required
def update_destination(dest_id: int):
    name = request.form.get("name", "").strip()
    province = request.form.get("province", "").strip()
    img = request.form.get("image_url", "").strip()
    if img and not (img.startswith("http://") or img.startswith("https://")):
        img = ""

    # Upload file ảnh từ máy nếu có
    image_file = request.files.get("image_file")
    image_public_id = None
    image_source = None
    if image_file and image_file.filename:
        try:
            upload_res = upload_image_file(image_file, province, name)
            if upload_res:
                image_public_id = upload_res["public_id"]
                img = upload_res["secure_url"]
                image_source = "admin_upload"
                flash("Đã tải ảnh mới lên Cloudinary thành công!", "success")
        except Exception as e:
            flash(f"Lỗi tải ảnh lên Cloudinary ({e}), giữ ảnh hiện tại.", "warning")

    data = {
        "name": name,
        "province": province,
        "address": request.form.get("address", "").strip(),
        "latitude": float(request.form.get("latitude", 0)),
        "longitude": float(request.form.get("longitude", 0)),
        "description": request.form.get("description", "").strip(),
        "image_url": img,
        "category_id": int(request.form.get("category_id")) if request.form.get("category_id") else None,
        "price_range": int(request.form.get("price_range", 1)),
        "noise_level": int(request.form.get("noise_level", 3)),
        "duration_hours": float(request.form.get("duration_hours", 1.0)),
        "is_outdoor": request.form.get("is_outdoor") == "1",
        "ticket_price": int(request.form.get("ticket_price", 0)),
        "is_active": request.form.get("is_active") == "1",
        "tags": tuple(request.form.getlist("tags")),
        "opening_hours": None,
    }
    if image_public_id:
        data["image_public_id"] = image_public_id
        data["image_source"] = image_source

    current_app.repo.save_destination(data, destination_id=dest_id)
    flash("Đã cập nhật địa điểm thành công!", "success")
    return redirect(url_for("admin.destinations_view"))


@admin_bp.route("/destinations/<int:dest_id>/delete", methods=["POST"])
@admin_required
def delete_destination(dest_id: int):
    current_app.repo.delete_destination(dest_id)
    flash("Đã chuyển địa điểm sang trạng thái ẩn (xóa mềm).", "info")
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


@admin_bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@admin_required
def delete_category_view(cat_id: int):
    ok = current_app.repo.delete_category(cat_id)
    if not ok:
        flash("Không thể xóa danh mục vì vẫn còn địa điểm trực thuộc đang hoạt động.", "danger")
    else:
        flash("Đã xóa danh mục thành công.", "info")
    return redirect(url_for("admin.categories_view"))

