import logging
import re
from urllib.parse import unquote, urlparse

from flask import Blueprint, jsonify, request, redirect, render_template
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash

from ..db import SessionLocal, User
from ..utils.roles import normalize_role
from ..extensions import login_manager
from ..utils.rate_limit import check_rate_limit, get_client_ip

bp = Blueprint("auth", __name__)
logger = logging.getLogger("liftcrm.auth")


_ALLOWED_NEXT_PATHS = {"/", "/admin", "/mobile"}


def normalize_next(next_url):
    if not next_url:
        return ""
    value = unquote(str(next_url)).strip()
    value = value.replace("\\", "/")
    value = re.sub(r"/+", "/", value)
    return value


def safe_next_target(next_url):
    candidate = normalize_next(next_url)
    if not candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return "/"
    if ":" in candidate.split("/", 1)[0]:
        return "/"
    if parsed.path not in _ALLOWED_NEXT_PATHS:
        return "/"
    if parsed.query:
        return f"{parsed.path}?{parsed.query}"
    return parsed.path


def role_redirect_target(user, next_url):
    safe_next = safe_next_target(next_url)
    if normalize_role(user.role) == "technician":
        return "/mobile"
    if safe_next == "/mobile":
        return "/admin"
    return safe_next


@login_manager.user_loader
def load_user(user_id):
    with SessionLocal() as db:
        return db.get(User, int(user_id))


@bp.post("/api/login")
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    ip = get_client_ip(request)
    rate_key = f"login:{ip}:{username}"
    allowed, info = check_rate_limit(rate_key, limit=10, window_seconds=600)
    if not allowed:
        logger.warning(
            "login_rate_limited",
            extra={"username": username, "ip": ip, "reset_in_seconds": info["reset_in_seconds"]},
        )
        response = jsonify(
            {
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many login attempts. Try again later.",
                }
            }
        )
        response.status_code = 429
        if info["reset_in_seconds"]:
            response.headers["Retry-After"] = str(info["reset_in_seconds"])
        return response
    with SessionLocal() as db:
        user = db.query(User).filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            logger.info(
                "login_attempt",
                extra={"username": username, "ip": ip, "success": False, "remaining": info["remaining"]},
            )
            return jsonify({"error": "Неверный логин или пароль"}), 400
        if not getattr(user, "is_active", 1):
            logger.info(
                "login_attempt",
                extra={"username": username, "ip": ip, "success": False, "remaining": info["remaining"], "disabled": True},
            )
            return jsonify({"error": "Аккаунт отключен"}), 403
        if user.role != normalize_role(user.role):
            user.role = normalize_role(user.role)
            db.commit()
    login_user(user)
    logger.info(
        "login_attempt",
        extra={"username": username, "ip": ip, "success": True, "remaining": info["remaining"]},
    )
    return jsonify(
        {
            "ok": True,
            "role": user.role,
            "username": user.username,
            "master_id": user.master_id,
            "is_active": bool(getattr(user, "is_active", 1)),
        }
    )


@bp.post("/login")
def login_form():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = request.form.get("next") or request.form.get("redirect_to") or "/"
    next_url = safe_next_target(next_url)
    ip = get_client_ip(request)
    rate_key = f"login:{ip}:{username}"
    allowed, info = check_rate_limit(rate_key, limit=10, window_seconds=600)
    if not allowed:
        logger.warning(
            "login_rate_limited",
            extra={"username": username, "ip": ip, "reset_in_seconds": info["reset_in_seconds"]},
        )
        response = render_template(
            "login.html",
            next_url=next_url,
            error="Слишком много попыток входа. Попробуйте позже.",
        )
        return response, 429
    with SessionLocal() as db:
        user = db.query(User).filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            logger.info(
                "login_attempt",
                extra={"username": username, "ip": ip, "success": False, "remaining": info["remaining"]},
            )
            return render_template(
                "login.html",
                next_url=next_url,
                error="Неверный логин или пароль",
            ), 400
        if not getattr(user, "is_active", 1):
            logger.info(
                "login_attempt",
                extra={
                    "username": username,
                    "ip": ip,
                    "success": False,
                    "remaining": info["remaining"],
                    "disabled": True,
                },
            )
            return render_template(
                "login.html",
                next_url=next_url,
                error="Аккаунт отключен",
            ), 403
        if user.role != normalize_role(user.role):
            user.role = normalize_role(user.role)
            db.commit()
    login_user(user)
    logger.info(
        "login_attempt",
        extra={"username": username, "ip": ip, "success": True, "remaining": info["remaining"]},
    )
    return redirect(role_redirect_target(user, next_url))


@bp.get("/login")
def login_page():
    next_url = request.args.get("next") or "/"
    return render_template("login.html", next_url=safe_next_target(next_url))


@bp.post("/api/logout")
@login_required
def api_logout():
    logout_user()
    return jsonify({"ok": True})


@bp.get("/logout")
def logout_page():
    logout_user()
    return redirect("/login")


@bp.post("/logout")
def logout_form():
    logout_user()
    return redirect("/login")


@bp.get("/api/me")
def api_me():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False})
    return jsonify(
        {
            "authenticated": True,
            "username": current_user.username,
            "role": current_user.role,
            "master_id": current_user.master_id,
            "is_active": bool(getattr(current_user, "is_active", 1)),
        }
    )
