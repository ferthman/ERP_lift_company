from flask import Blueprint, jsonify, request
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash

from ..db import SessionLocal, User
from ..extensions import login_manager

bp = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id):
    with SessionLocal() as db:
        return db.get(User, int(user_id))


@bp.post("/api/login")
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    with SessionLocal() as db:
        user = db.query(User).filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Неверный логин или пароль"}), 400
    login_user(user)
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
