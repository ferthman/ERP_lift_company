from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import login_required
from werkzeug.security import generate_password_hash

from ..db import SessionLocal, User, Master, Ticket
from ..utils.security import role_required, generate_temp_password
from ..tickets.service import bump_ticket_version
from ..utils.roles import ALLOWED_ROLES, ROLE_TECHNICIAN, normalize_role, is_technician

bp = Blueprint("access", __name__)


def _unique_username(db, base):
    candidate = base
    counter = 1
    while db.query(User).filter(User.username == candidate).first():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _serialize_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": bool(getattr(user, "is_active", 1)),
        "master_id": user.master_id,
        "master_name": user.master.name if user.master else None,
        "master_phone": user.master.phone if user.master else None,
    }


@bp.get("/api/users")
@login_required
@role_required("admin")
def list_users():
    with SessionLocal() as db:
        users = db.query(User).order_by(User.id).all()
        return jsonify([_serialize_user(u) for u in users])


@bp.patch("/api/users/<int:user_id>")
@login_required
@role_required("admin")
def update_user(user_id):
    data = request.get_json() or {}
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        role = normalize_role(data.get("role")) if "role" in data else user.role
        if role not in ALLOWED_ROLES:
            return jsonify({"error": "Invalid role"}), 400

        master_id = user.master_id
        if "master_id" in data:
            incoming_master = data.get("master_id")
            if incoming_master in ("", None):
                master_id = None
            else:
                try:
                    master_id = int(incoming_master)
                except Exception:
                    return jsonify({"error": "Invalid master_id"}), 400
                master = db.get(Master, master_id)
                if not master:
                    return jsonify({"error": "Master not found"}), 404

        if is_technician(role):
            if master_id is None:
                return jsonify({"error": "Technician must have master_id"}), 400
        elif master_id is not None:
            return jsonify({"error": "Non-technician cannot have master_id"}), 400

        if master_id is not None:
            existing = db.query(User).filter(User.master_id == master_id, User.id != user.id).first()
            if existing:
                return jsonify({"error": "Master already linked to another user"}), 409

        if "is_active" in data:
            user.is_active = 1 if data.get("is_active") else 0

        user.role = role
        user.master_id = master_id
        db.commit()
        db.refresh(user)
        return jsonify(_serialize_user(user))


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


@bp.post("/api/masters/<int:master_id>/assign-role")
@login_required
@role_required("admin")
def assign_role(master_id):
    data = request.get_json() or {}
    role = normalize_role(data.get("role") or ROLE_TECHNICIAN)
    if role != ROLE_TECHNICIAN:
        return jsonify({"error": "Only TECHNICIAN can be assigned to master"}), 400
    username = (data.get("username") or "").strip()
    with SessionLocal() as db:
        master = db.get(Master, master_id)
        if not master:
            return jsonify({"error": "Master not found"}), 404
        existing = db.query(User).filter(User.master_id == master_id).first()
        if existing:
            return jsonify({"error": "User already linked to master"}), 409
        if username:
            if db.query(User).filter(User.username == username).first():
                return jsonify({"error": "Username already exists"}), 400
        else:
            username = _unique_username(db, f"master{master_id}")
        temp_password = generate_temp_password()
        user = User(
            username=username,
            password_hash=generate_password_hash(temp_password),
            role=role,
            master_id=master_id,
            is_active=1,
        )
        db.add(user)
        db.commit()
        return jsonify(
            {
                "ok": True,
                "user_id": user.id,
                "username": user.username,
                "temp_password": temp_password,
                "master_id": master_id,
            }
        )


@bp.post("/api/access/replace-technician")
@login_required
@role_required("admin")
def replace_technician():
    data = request.get_json() or {}
    old_master_id = data.get("old_master_id")
    new_master_id = data.get("new_master_id")
    new_profile = data.get("new_master_profile")
    reassign_open = bool(data.get("reassign_open_tickets"))
    disable_old_user = bool(data.get("disable_old_user"))
    deactivate_old_master = bool(data.get("deactivate_old_master"))

    try:
        old_master_id = int(old_master_id)
    except Exception:
        return jsonify({"error": "Invalid old_master_id"}), 400

    if new_master_id is not None and new_profile:
        return jsonify({"error": "Provide either new_master_id or new_master_profile"}), 400

    with SessionLocal() as db:
        old_master = db.get(Master, old_master_id)
        if not old_master:
            return jsonify({"error": "Old master not found"}), 404

        created_master = None
        if new_profile:
            name = (new_profile.get("name") or "").strip()
            phone = (new_profile.get("phone") or "").strip()
            phone = phone if phone else None
            if not name:
                return jsonify({"error": "New master name is required"}), 400
            created_master = Master(name=name, phone=phone, is_active=1)
            db.add(created_master)
            db.commit()
            db.refresh(created_master)
            new_master_id = created_master.id
        elif new_master_id is not None:
            try:
                new_master_id = int(new_master_id)
            except Exception:
                return jsonify({"error": "Invalid new_master_id"}), 400
            if new_master_id == old_master_id:
                return jsonify({"error": "new_master_id must differ from old_master_id"}), 400
            if not db.get(Master, new_master_id):
                return jsonify({"error": "New master not found"}), 404
        else:
            return jsonify({"error": "New master is required"}), 400

        reassigned_count = 0
        if reassign_open:
            open_statuses = ["NEW", "ASSIGNED", "ACCEPTED", "IN_PROGRESS", "WAITING"]
            rows = (
                db.query(Ticket)
                .filter(
                    Ticket.assigned_master_id == old_master_id,
                    Ticket.status.in_(open_statuses),
                    Ticket.archived_at.is_(None),
                )
                .all()
            )
            for t in rows:
                t.assigned_master_id = new_master_id
                t.assigned_at = datetime.now(timezone.utc)
                bump_ticket_version(t)
            reassigned_count = len(rows)

        disabled_users = 0
        if disable_old_user:
            linked = db.query(User).filter(User.master_id == old_master_id).all()
            for user in linked:
                user.is_active = 0
                disabled_users += 1

        if deactivate_old_master:
            old_master.is_active = 0

        db.commit()
        return jsonify(
            {
                "ok": True,
                "new_master_id": new_master_id,
                "reassigned_tickets": reassigned_count,
                "disabled_users": disabled_users,
                "deactivated_master": bool(deactivate_old_master),
            }
        )
