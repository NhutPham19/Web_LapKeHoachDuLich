from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import login_required
from app.contracts import INTERESTS, TRAVEL_STYLES

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()

        if not email or "@" not in email:
            flash("Vui lòng nhập địa chỉ email hợp lệ.", "danger")
            return render_template("register.html"), 400
        if len(password) < 8:
            flash("Mật khẩu phải có độ dài tối thiểu 8 ký tự.", "danger")
            return render_template("register.html"), 400
        if not full_name:
            flash("Vui lòng nhập họ và tên của bạn.", "danger")
            return render_template("register.html"), 400

        existing = current_app.repo.get_user_by_email(email)
        if existing:
            flash("Địa chỉ email này đã được đăng ký tài khoản.", "danger")
            return render_template("register.html"), 400

        pwd_hash = generate_password_hash(password)
        user_id = current_app.repo.create_user(email, pwd_hash, full_name)

        # Chống session fixation
        csrf_tok = session.get("csrf_token")
        session.clear()
        if csrf_tok:
            session["csrf_token"] = csrf_tok

        session["user"] = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "is_admin": False,
        }
        flash("Đăng ký tài khoản thành công! Hãy chọn sở thích du lịch của bạn.", "success")
        return redirect(url_for("auth.onboarding"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = current_app.repo.get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Email hoặc mật khẩu không chính xác.", "danger")
            return render_template("login.html"), 400

        # Chống session fixation
        csrf_tok = session.get("csrf_token")
        session.clear()
        if csrf_tok:
            session["csrf_token"] = csrf_tok

        session["user"] = {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "is_admin": user.get("is_admin", False),
        }
        flash(f"Chào mừng trở lại, {user['full_name']}!", "success")

        next_url = request.args.get("next")
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("trips.list_trips_view"))

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Bạn đã đăng xuất an toàn.", "info")
    return redirect("/")


@auth_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    user_id = session["user"]["id"]
    if request.method == "POST":
        interests = request.form.getlist("interests")
        travel_style = request.form.get("travel_style")

        valid_interests = [i for i in interests if i in INTERESTS]
        if not valid_interests:
            flash("Vui lòng chọn ít nhất 1 sở thích du lịch.", "warning")
            return render_template("onboarding.html", user_interests=interests, user_style=travel_style), 400

        if travel_style not in TRAVEL_STYLES:
            flash("Phong cách du lịch không hợp lệ.", "warning")
            return render_template("onboarding.html", user_interests=interests, user_style=travel_style), 400

        current_app.repo.save_preferences(user_id, tuple(valid_interests), travel_style)
        flash("Đã lưu sở thích du lịch thành công!", "success")
        return redirect(url_for("trips.new_trip_view"))

    prefs = current_app.repo.get_preferences(user_id)
    return render_template(
        "onboarding.html",
        user_interests=prefs.get("interests", []),
        user_style=prefs.get("travel_style", "thoai_mai"),
    )
