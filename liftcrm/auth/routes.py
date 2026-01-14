import logging

from flask import Blueprint, jsonify, request
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash

from ..db import SessionLocal, User
from ..extensions import login_manager
from ..utils.rate_limit import check_rate_limit, get_client_ip

bp = Blueprint("auth", __name__)
logger = logging.getLogger("liftcrm.auth")


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
    login_user(user)
    logger.info(
        "login_attempt",
        extra={"username": username, "ip": ip, "success": True, "remaining": info["remaining"]},
    )
    return jsonify({"ok": True, "role": user.role, "username": user.username, "master_id": user.master_id})


@bp.post("/api/logout")
@login_required
def api_logout():
    logout_user()
    return jsonify({"ok": True})


@bp.get("/api/me")
def api_me():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False})
    return jsonify(
        {"authenticated": True, "username": current_user.username, "role": current_user.role, "master_id": current_user.master_id}
    )
