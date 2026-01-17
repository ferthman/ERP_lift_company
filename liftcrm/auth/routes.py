import logging

from flask import Blueprint, jsonify, request
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import SessionLocal, User, Master
from ..extensions import login_manager
from ..utils.rate_limit import check_rate_limit, get_client_ip
from ..utils.security import role_required, generate_temp_password
from ..utils.users import normalize_role, validate_role_master_id, ROLE_TECHNICIAN

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


def _unique_username(db, base):
    candidate = base
    counter = 1
    while db.query(User).filter(User.username == candidate).first():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


@bp.post("/api/users")
@login_required
@role_required("admin")
def create_user():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    role = normalize_role(data.get("role"))
    master_id = data.get("master_id")
    password = data.get("password")
    if master_id is not None:
        try:
            master_id = int(master_id)
        except ValueError:
            return jsonify({"error": "Invalid master_id"}), 400
    error = validate_role_master_id(role, master_id)
    if error:
        return jsonify({"error": error}), 400
    with SessionLocal() as db:
        if master_id is not None:
            master = db.get(Master, master_id)
            if not master:
                return jsonify({"error": "Master not found"}), 404
            existing = db.query(User).filter(User.master_id == master_id).first()
            if existing:
                return jsonify({"error": "Master already linked"}), 409
        if not username:
            if role == ROLE_TECHNICIAN and master_id is not None:
                username = _unique_username(db, f"master{master_id}")
            else:
                username = _unique_username(db, role)
        elif db.query(User).filter(User.username == username).first():
            return jsonify({"error": "Username already exists"}), 409
        temp_password = password or generate_temp_password()
        user = User(
            username=username,
            password_hash=generate_password_hash(temp_password),
            role=role,
            master_id=master_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return jsonify(
            {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "master_id": user.master_id,
                "temp_password": temp_password,
            }
        ), 201


@bp.post("/api/users/<int:user_id>/reset-password")
@login_required
@role_required("admin")
def reset_user_password(user_id):
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        temp_password = generate_temp_password()
        user.password_hash = generate_password_hash(temp_password)
        db.commit()
        return jsonify({"ok": True, "username": user.username, "temp_password": temp_password})
