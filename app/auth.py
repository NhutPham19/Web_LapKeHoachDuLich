from functools import wraps
from flask import abort, flash, redirect, request, session, url_for


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user"):
            if request.path.startswith("/api/"):
                return {"error": "unauthorized", "message": "Vui lòng đăng nhập"}, 401
            flash("Vui lòng đăng nhập để tiếp tục.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get("user")
        if not user or not user.get("is_admin"):
            if request.path.startswith("/api/"):
                return {"error": "forbidden", "message": "Bạn không có quyền quản trị"}, 403
            abort(403)
        return f(*args, **kwargs)

    return decorated_function
