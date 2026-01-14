import logging
import os
import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_from_directory
from flask_login import login_required, current_user

from .service import auto_assign_master, haversine_m, send_report, validate_status_transition
from . import repository
from ..db import SessionLocal, Master, Ticket, Attachment, User, AuditLog
from ..objects.service import upsert_object_from_ticket
from ..utils.security import role_required
from ..utils.time import to_utc
from ..utils.audit import log_audit, changed_fields
from .. import config

bp = Blueprint("tickets", __name__)
logger = logging.getLogger(__name__)

ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp"}
CLOSE_REASONS = [
    "EQUIPMENT_FAILURE",
    "PASSENGER_TRAPPED",
    "FALSE_CALL",
    "POWER_ISSUE",
    "EXTERNAL_REASON",
    "OTHER",
]

PRIORITY_VALUES = ["HIGH", "MEDIUM", "LOW"]


def _transition_error(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message}}), status


@bp.get("/api/masters")
@login_required
def list_masters():
    with SessionLocal() as db:
        ms = db.query(Master).order_by(Master.id).all()
        return jsonify(
            [
                {"id": m.id, "name": m.name, "is_active": bool(m.is_active), "username": m.user.username if m.user else None}
                for m in ms
            ]
        )


@bp.post("/api/masters")
@login_required
@role_required("admin")
def create_master():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    with SessionLocal() as db:
        m = Master(name=name, is_active=1)
        db.add(m)
        db.commit()
        db.refresh(m)
        from werkzeug.security import generate_password_hash

        u = User(
            username=f"master{m.id}",
            password_hash=generate_password_hash(config.MASTER_PASSWORD),
            role="master",
            master_id=m.id,
        )
        db.add(u)
        db.commit()
        return jsonify({"id": m.id, "name": m.name, "username": u.username, "temp_password": config.MASTER_PASSWORD}), 201


@bp.delete("/api/masters/<int:master_id>")
@login_required
@role_required("admin")
def delete_master(master_id):
    with SessionLocal() as db:
        m = db.get(Master, master_id)
        if not m:
            return jsonify({"error": "Master not found"}), 404
        others = db.query(Master).filter(Master.id != master_id, Master.is_active == 1).all()
        if not others:
            return jsonify({"error": "Нельзя удалить единственного активного мастера"}), 400
        open_statuses = ["NEW", "ASSIGNED", "IN_PROGRESS"]
        open_tickets = (
            db.query(Ticket)
            .filter(
                Ticket.assigned_master_id == master_id,
                Ticket.status.in_(open_statuses),
                Ticket.archived_at.is_(None),
            )
            .all()
        )
        counts = {x.id: 0 for x in others}
        rows = (
            db.query(Ticket.assigned_master_id, repository.func.count(Ticket.id))
            .filter(
                Ticket.status.in_(open_statuses),
                Ticket.assigned_master_id.in_([x.id for x in others]),
                Ticket.archived_at.is_(None),
            )
            .group_by(Ticket.assigned_master_id)
            .all()
        )
        for mid, cnt in rows:
            counts[mid] = cnt
        for t in open_tickets:
            new_id = min(counts, key=lambda k: (counts[k], k))
            t.assigned_master_id = new_id
            t.assigned_at = datetime.now(timezone.utc)
            if t.status in ["NEW", "ASSIGNED"]:
                t.status = "ASSIGNED"
            counts[new_id] += 1
        for u in db.query(User).filter(User.master_id == master_id).all():
            db.delete(u)
        db.delete(m)
        db.commit()
        return jsonify({"ok": True, "reassigned": len(open_tickets)})


@bp.patch("/api/masters/<int:master_id>/toggle_active")
@login_required
@role_required("admin")
def toggle_master_active(master_id):
    with SessionLocal() as db:
        m = db.get(Master, master_id)
        if not m:
            return jsonify({"error": "Master not found"}), 404
        m.is_active = 0 if m.is_active else 1
        reassigned = 0
        if m.is_active == 0:
            others = db.query(Master).filter(Master.id != master_id, Master.is_active == 1).all()
            if not others:
                return jsonify({"error": "Нет других активных мастеров для перераспределения"}), 400
            open_statuses = ["NEW", "ASSIGNED", "IN_PROGRESS"]
            open_tickets = (
                db.query(Ticket)
                .filter(
                    Ticket.assigned_master_id == master_id,
                    Ticket.status.in_(open_statuses),
                    Ticket.archived_at.is_(None),
                )
                .all()
            )
            counts = {x.id: 0 for x in others}
            rows = (
                db.query(Ticket.assigned_master_id, repository.func.count(Ticket.id))
                .filter(
                    Ticket.status.in_(open_statuses),
                    Ticket.assigned_master_id.in_([x.id for x in others]),
                    Ticket.archived_at.is_(None),
                )
                .group_by(Ticket.assigned_master_id)
                .all()
            )
            for mid, cnt in rows:
                counts[mid] = cnt
            for t in open_tickets:
                new_id = min(counts, key=lambda k: (counts[k], k))
                t.assigned_master_id = new_id
                t.assigned_at = datetime.now(timezone.utc)
                if t.status in ["NEW", "ASSIGNED"]:
                    t.status = "ASSIGNED"
                counts[new_id] += 1
            reassigned = len(open_tickets)
        db.commit()
        return jsonify({"ok": True, "is_active": bool(m.is_active), "reassigned": reassigned})


@bp.get("/api/tickets")
@login_required
def list_tickets():
    include_archived = request.args.get("include_archived") in {"1", "true", "True"}
    unassigned_only = request.args.get("unassigned") in {"1", "true", "True"}
    overdue_only = request.args.get("overdue") in {"1", "true", "True"}
    master_id = request.args.get("master_id")
    priority = request.args.get("priority")
    if priority:
        priority = str(priority).upper()
        if priority not in PRIORITY_VALUES:
            return jsonify({"error": "Invalid priority"}), 400
    if master_id:
        try:
            master_id = int(master_id)
        except ValueError:
            return jsonify({"error": "Invalid master_id"}), 400
    with SessionLocal() as db:
        query = db.query(Ticket).order_by(Ticket.created_at.desc())
        if not include_archived:
            query = query.filter(Ticket.archived_at.is_(None))
        if unassigned_only:
            query = query.filter(Ticket.assigned_master_id.is_(None))
        if master_id:
            query = query.filter(Ticket.assigned_master_id == master_id)
        if priority:
            query = query.filter(Ticket.priority == priority)
        tickets = query.all()
        if overdue_only:
            filtered = []
            for t in tickets:
                sla = repository.compute_sla_fields(t)
                if sla["sla_response_breached"] or sla["sla_completion_breached"]:
                    filtered.append(t)
            tickets = filtered
        return jsonify([repository.serialize_ticket(t) for t in tickets])


@bp.post("/api/tickets")
@login_required
@role_required("admin", "dispatcher")
def create_ticket():
    data = request.get_json() or {}
    for k in ("object_name", "lat", "lon"):
        if k not in data:
            return jsonify({"error": f"Missing field: {k}"}), 400
    priority = (data.get("priority") or "MEDIUM").upper()
    if priority not in PRIORITY_VALUES:
        return jsonify({"error": "Invalid priority"}), 400

    def _parse_custom(val):
        if val in (None, ""):
            return None
        try:
            num = int(val)
        except Exception:
            return "INVALID"
        if num <= 0:
            return "INVALID"
        return num

    custom_resp = _parse_custom(data.get("custom_sla_response_minutes"))
    custom_comp = _parse_custom(data.get("custom_sla_completion_minutes"))
    if custom_resp == "INVALID" or custom_comp == "INVALID":
        return jsonify({"error": "custom SLA minutes must be positive integers"}), 400
    with SessionLocal() as db:
        t = Ticket(
            object_name=data["object_name"],
            address=data.get("address"),
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            description=data.get("description"),
            priority=priority,
            email=data.get("email"),
            status="NEW",
            custom_sla_response_minutes=custom_resp,
            custom_sla_completion_minutes=custom_comp,
        )
        m = auto_assign_master(db)
        if m:
            t.assigned_master_id, t.status = m.id, "ASSIGNED"
            t.assigned_at = datetime.now(timezone.utc)
        db.add(t)
        db.flush()
        snapshot_fields = [
            "object_name",
            "address",
            "lat",
            "lon",
            "priority",
            "custom_sla_response_minutes",
            "custom_sla_completion_minutes",
            "description",
            "assigned_master_id",
            "status",
        ]
        new = {field: getattr(t, field, None) for field in snapshot_fields}
        log_audit(
            db,
            entity_type="ticket",
            entity_id=t.id,
            action="CREATE",
            actor_user_id=current_user.id,
            old={},
            new=new,
        )
        db.commit()
        db.refresh(t)
    try:
        upsert_object_from_ticket(t.object_name, t.address, t.lat, t.lon, ticket_id=t.id)
    except Exception:
        logger.warning("objects upsert failed", extra={"ticket_id": t.id}, exc_info=True)
    return jsonify({"id": t.id, "assigned_master_id": t.assigned_master_id, "status": t.status}), 201


@bp.patch("/api/tickets/<int:ticket_id>")
@login_required
@role_required("admin", "dispatcher")
def update_ticket(ticket_id):
    data = request.get_json() or {}

    def _parse_custom(val):
        if val in (None, ""):
            return None
        try:
            num = int(val)
        except Exception:
            return "INVALID"
        if num <= 0:
            return "INVALID"
        return num

    priority = data.get("priority")
    if priority is not None:
        priority = str(priority).upper()
        if priority not in PRIORITY_VALUES:
            return jsonify({"error": "Invalid priority"}), 400

    custom_resp = _parse_custom(data.get("custom_sla_response_minutes"))
    custom_comp = _parse_custom(data.get("custom_sla_completion_minutes"))
    if custom_resp == "INVALID" or custom_comp == "INVALID":
        return jsonify({"error": "custom SLA minutes must be positive integers"}), 400

    description = data.get("description") if "description" in data else None
    if priority is None and custom_resp is None and custom_comp is None and description is None:
        return jsonify({"error": "No fields to update"}), 400
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        old_snapshot = {
            "priority": t.priority,
            "custom_sla_response_minutes": t.custom_sla_response_minutes,
            "custom_sla_completion_minutes": t.custom_sla_completion_minutes,
            "description": t.description,
        }
        if priority is not None:
            t.priority = priority
        if custom_resp is not None:
            t.custom_sla_response_minutes = custom_resp
        if custom_comp is not None:
            t.custom_sla_completion_minutes = custom_comp
        if description is not None:
            t.description = description
        old, new = changed_fields(
            old_snapshot,
            t,
            [
                "priority",
                "custom_sla_response_minutes",
                "custom_sla_completion_minutes",
                "description",
            ],
        )
        if old or new:
            log_audit(
                db,
                entity_type="ticket",
                entity_id=t.id,
                action="EDIT",
                actor_user_id=current_user.id,
                old=old,
                new=new,
            )
        db.commit()
        db.refresh(t)
        return jsonify(repository.serialize_ticket(t))


@bp.post("/api/tickets/<int:ticket_id>/reassign")
@login_required
@role_required("admin", "dispatcher")
def reassign_ticket(ticket_id):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        m = auto_assign_master(db)
        if not m:
            return jsonify({"error": "No active masters available"}), 400
        old_status = t.status
        old_assigned = t.assigned_master_id
        t.assigned_master_id = m.id
        t.assigned_at = datetime.now(timezone.utc)
        if t.status in ["NEW", "ASSIGNED"]:
            t.status = "ASSIGNED"
            ok, code, message = validate_status_transition(
                old_status,
                t.status,
                t,
                current_user.role,
                {},
            )
            if not ok:
                return _transition_error(code, message)
        log_audit(
            db,
            entity_type="ticket",
            entity_id=t.id,
            action="ASSIGN",
            actor_user_id=current_user.id,
            old={"assigned_master_id": old_assigned, "status": old_status},
            new={"assigned_master_id": t.assigned_master_id, "status": t.status},
        )
        db.commit()
        return jsonify({"message": "Reassigned", "assigned_master_id": t.assigned_master_id})


@bp.post("/api/tickets/<int:ticket_id>/cancel")
@login_required
@role_required("admin", "dispatcher")
def cancel_ticket(ticket_id):
    data = request.get_json() or {}
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        if t.status == "CANCELLED":
            return jsonify({"message": "Already cancelled"}), 200
        old_status = t.status
        old_reason = t.close_reason
        old_comment = t.close_comment
        close_reason = data.get("close_reason")
        close_comment = data.get("close_comment")
        t.status = "CANCELLED"
        payload = {"close_reason": close_reason, "close_comment": close_comment}
        ok, code, message = validate_status_transition(
            old_status,
            t.status,
            t,
            current_user.role,
            payload,
        )
        if not ok:
            status = 403 if code == "FORBIDDEN" else 400
            return _transition_error(code, message, status=status)
        t.close_reason = close_reason
        t.close_comment = str(close_comment).strip()
        old, new = changed_fields(
            {"status": old_status, "close_reason": old_reason, "close_comment": old_comment},
            t,
            ["status", "close_reason", "close_comment"],
        )
        if old or new:
            log_audit(
                db,
                entity_type="ticket",
                entity_id=t.id,
                action="CANCEL",
                actor_user_id=current_user.id,
                old=old,
                new=new,
            )
        db.commit()
        return jsonify({"message": "Cancelled"})


@bp.get("/api/tickets/<int:ticket_id>")
@login_required
def get_ticket(ticket_id):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        return jsonify(repository.serialize_ticket(t))


@bp.post("/api/tickets/<int:ticket_id>/arrive")
@login_required
def arrive_ticket(ticket_id):
    if current_user.role != "master":
        return jsonify({"error": "Only master can mark arrival"}), 403
    data = request.get_json() or {}
    lat = data.get("lat")
    lon = data.get("lon")
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        if not t.assigned_master_id:
            ok, code, message = validate_status_transition(
                t.status,
                "IN_PROGRESS",
                t,
                current_user.role,
                {},
            )
            return _transition_error(code, message)
        if t.assigned_master_id != current_user.master_id:
            return jsonify({"error": "Ticket not assigned to you"}), 403
        if lat is None or lon is None:
            return jsonify({"error": "lat/lon required"}), 400
        dist = haversine_m(float(lat), float(lon), t.lat, t.lon)
        if dist > 500:
            return jsonify({"error": f"Outside geofence ({int(dist)} m > 500 m)"}), 403
        old_status = t.status
        old_arrived = t.arrived_at
        t.status = "IN_PROGRESS"
        t.arrived_at = datetime.now(timezone.utc)
        t.arrival_lat = float(lat)
        t.arrival_lon = float(lon)
        ok, code, message = validate_status_transition(
            old_status,
            t.status,
            t,
            current_user.role,
            {},
        )
        if not ok:
            return _transition_error(code, message)
        old, new = changed_fields(
            {"status": old_status, "arrived_at": old_arrived},
            t,
            ["status", "arrived_at"],
        )
        if old or new:
            log_audit(
                db,
                entity_type="ticket",
                entity_id=t.id,
                action="STATUS_CHANGE",
                actor_user_id=current_user.id,
                old=old,
                new=new,
            )
        db.commit()
        return jsonify({"message": "Arrived", "distance_m": int(dist), "status": t.status})


@bp.post("/api/tickets/<int:ticket_id>/complete")
@login_required
def complete_ticket(ticket_id):
    if current_user.role != "master":
        return jsonify({"error": "Only master can complete"}), 403
    data = request.get_json() or {}
    lat = data.get("lat")
    lon = data.get("lon")
    close_reason = data.get("close_reason")
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        if not t.assigned_master_id:
            ok, code, message = validate_status_transition(
                t.status,
                "COMPLETED",
                t,
                current_user.role,
                {},
            )
            return _transition_error(code, message)
        if t.assigned_master_id != current_user.master_id:
            return jsonify({"error": "Ticket not assigned to you"}), 403
        if lat is None or lon is None:
            return jsonify({"error": "lat/lon required"}), 400
        if not close_reason:
            return jsonify({"error": "close_reason is required"}), 400
        if close_reason not in CLOSE_REASONS:
            return jsonify({"error": "Invalid close_reason"}), 400
        dist = haversine_m(float(lat), float(lon), t.lat, t.lon)
        if dist > 500:
            return jsonify({"error": f"Outside geofence ({int(dist)} m > 500 m)"}), 403
        old_status = t.status
        old_completed = t.completed_at
        old_reason = t.close_reason
        t.status = "COMPLETED"
        t.completed_at = datetime.now(timezone.utc)
        t.completion_lat = float(lat)
        t.completion_lon = float(lon)
        t.close_reason = close_reason
        ok, code, message = validate_status_transition(
            old_status,
            t.status,
            t,
            current_user.role,
            {},
        )
        if not ok:
            return _transition_error(code, message)
        old, new = changed_fields(
            {"status": old_status, "completed_at": old_completed, "close_reason": old_reason},
            t,
            ["status", "completed_at", "close_reason"],
        )
        if old or new:
            log_audit(
                db,
                entity_type="ticket",
                entity_id=t.id,
                action="STATUS_CHANGE",
                actor_user_id=current_user.id,
                old=old,
                new=new,
            )
        db.commit()
        try:
            send_report(t)
        except Exception as e:
            print("Report sending failed:", e)
        return jsonify({"message": "Completed", "distance_m": int(dist), "status": t.status})


@bp.post("/api/tickets/<int:ticket_id>/upload")
@login_required
def upload_file(ticket_id):
    from werkzeug.utils import secure_filename
    from flask import current_app

    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        if current_user.role == "master" and t.assigned_master_id != current_user.master_id:
            return jsonify({"error": "Ticket not assigned to you"}), 403
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    if not ("." in f.filename and f.filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXTS):
        return jsonify({"error": "Only png/jpg/jpeg/webp allowed"}), 400
    fname = secure_filename(f.filename)
    unique = f"{int(datetime.now(timezone.utc).timestamp())}_{fname}"
    f.save(os.path.join(current_app.config["UPLOAD_FOLDER"], unique))
    with SessionLocal() as db:
        a = Attachment(ticket_id=ticket_id, filename=unique, orig_name=fname)
        db.add(a)
        db.flush()
        log_audit(
            db,
            entity_type="attachment",
            entity_id=a.id,
            action="CREATE",
            actor_user_id=current_user.id,
            old={},
            new={"ticket_id": ticket_id, "filename": unique, "orig_name": fname},
        )
        db.commit()
    return jsonify({"ok": True, "url": f"/uploads/{unique}", "name": fname})


@bp.get("/uploads/<path:filename>")
def serve_upload(filename):
    from flask import current_app

    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.post("/api/tickets/<int:ticket_id>/assign/<int:master_id>")
@login_required
@role_required("admin", "dispatcher")
def assign_ticket(ticket_id, master_id):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        m = db.get(Master, master_id)
        if not m:
            return jsonify({"error": "Master not found"}), 404
        if int(getattr(m, "is_active", 1)) != 1:
            return jsonify({"error": "Мастер неактивен"}), 400
        old_status = t.status
        old_assigned = t.assigned_master_id
        t.assigned_master_id = m.id
        t.assigned_at = datetime.now(timezone.utc)
        if t.status in ["NEW", "ASSIGNED"]:
            t.status = "ASSIGNED"
            ok, code, message = validate_status_transition(
                old_status,
                t.status,
                t,
                current_user.role,
                {},
            )
            if not ok:
                return _transition_error(code, message)
        log_audit(
            db,
            entity_type="ticket",
            entity_id=t.id,
            action="ASSIGN",
            actor_user_id=current_user.id,
            old={"assigned_master_id": old_assigned, "status": old_status},
            new={"assigned_master_id": t.assigned_master_id, "status": t.status},
        )
        db.commit()
        return jsonify({"message": "Assigned", "assigned_master_id": t.assigned_master_id, "assigned_master_name": m.name})


@bp.post("/api/tickets/<int:ticket_id>/archive")
@login_required
@role_required("admin", "dispatcher")
def archive_ticket(ticket_id):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if not t.archived_at:
            now = datetime.now(timezone.utc)
            old_archived = t.archived_at
            t.archived_at = now
            t.updated_at = now
            old, new = changed_fields(
                {"archived_at": old_archived},
                t,
                ["archived_at"],
            )
            if old or new:
                log_audit(
                    db,
                    entity_type="ticket",
                    entity_id=t.id,
                    action="ARCHIVE",
                    actor_user_id=current_user.id,
                    old=old,
                    new=new,
                )
            db.commit()
        archived_at = to_utc(t.archived_at).isoformat() if t.archived_at else None
        return jsonify({"ok": True, "archived_at": archived_at})


@bp.post("/api/tickets/<int:ticket_id>/unarchive")
@login_required
@role_required("admin", "dispatcher")
def unarchive_ticket(ticket_id):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            now = datetime.now(timezone.utc)
            old_archived = t.archived_at
            t.archived_at = None
            t.updated_at = now
            old, new = changed_fields(
                {"archived_at": old_archived},
                t,
                ["archived_at"],
            )
            if old or new:
                log_audit(
                    db,
                    entity_type="ticket",
                    entity_id=t.id,
                    action="UNARCHIVE",
                    actor_user_id=current_user.id,
                    old=old,
                    new=new,
                )
            db.commit()
        return jsonify({"ok": True, "archived_at": None})


@bp.get("/api/tickets/<int:ticket_id>/history")
@login_required
def ticket_history(ticket_id):
    limit = request.args.get("limit", 50)
    offset = request.args.get("offset", 0)
    try:
        limit = int(limit)
        offset = int(offset)
    except ValueError:
        return jsonify({"error": "Invalid pagination"}), 400
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if current_user.role == "master":
            if t.assigned_master_id != current_user.master_id:
                return jsonify({"error": "Forbidden"}), 403
        elif current_user.role not in {"admin", "dispatcher"}:
            return jsonify({"error": "Forbidden"}), 403
        rows = (
            db.query(AuditLog, User.username)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .filter(AuditLog.entity_type == "ticket", AuditLog.entity_id == ticket_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        items = []
        for log_entry, username in rows:
            try:
                diff = json.loads(log_entry.diff_json) if log_entry.diff_json else {}
            except json.JSONDecodeError:
                diff = {"raw": log_entry.diff_json}
            items.append(
                {
                    "action": log_entry.action,
                    "created_at": log_entry.created_at,
                    "actor_user_id": log_entry.actor_user_id,
                    "actor_username": username,
                    "diff": diff,
                }
            )
        return jsonify(items)


@bp.delete("/api/tickets/<int:ticket_id>")
@login_required
def delete_ticket(ticket_id):
    return (
        jsonify(
            {
                "error": {
                    "code": 405,
                    "message": "DELETE /api/tickets/<id> is deprecated. Use POST /api/tickets/<id>/archive.",
                }
            }
        ),
        405,
    )


@bp.get("/api/metrics")
@login_required
@role_required("admin", "dispatcher")
def metrics():
    from statistics import median

    with SessionLocal() as db:
        tickets = db.query(Ticket).filter(Ticket.archived_at.is_(None)).all()
        sla_infos = [repository.compute_sla_fields(t) for t in tickets]
        response_breaches = [info.get("sla_response_breached") for info in sla_infos]
        completion_breaches = [info.get("sla_completion_breached") for info in sla_infos]
        total_tickets = len(tickets)
        resp_breach_count = sum(1 for x in response_breaches if x)
        comp_breach_count = sum(1 for x in completion_breaches if x)
        reason_counts = {r: 0 for r in CLOSE_REASONS}
        reason_counts["UNSPECIFIED"] = 0
        sla_breaches_by_reason = {k: {"response": 0, "completion": 0} for k in reason_counts}
        counts = {"NEW": 0, "ASSIGNED": 0, "IN_PROGRESS": 0, "COMPLETED": 0, "CANCELLED": 0}
        priority_counts = {p: 0 for p in PRIORITY_VALUES}
        for t, info in zip(tickets, sla_infos):
            counts[t.status] = counts.get(t.status, 0) + 1
            priority_counts[t.priority or "MEDIUM"] = priority_counts.get(t.priority or "MEDIUM", 0) + 1
            if t.status == "COMPLETED":
                reason = t.close_reason if t.close_reason in CLOSE_REASONS else "UNSPECIFIED"
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                if info.get("sla_response_breached"):
                    sla_breaches_by_reason[reason]["response"] += 1
                if info.get("sla_completion_breached"):
                    sla_breaches_by_reason[reason]["completion"] += 1
        durs = [
            (to_utc(t.completed_at) - to_utc(t.created_at)).total_seconds() for t in tickets if t.completed_at and t.created_at
        ]
        overall = {
            "total": len(tickets),
            "counts": counts,
            "avg_close_sec": (sum(durs) / len(durs)) if durs else None,
            "median_close_sec": (median(durs) if durs else None),
        }
        masters = db.query(Master).all()
        masters_data = []
        for m in masters:
            mtickets = [t for t in tickets if t.assigned_master_id == m.id]
            m_counts = {"NEW": 0, "ASSIGNED": 0, "IN_PROGRESS": 0, "COMPLETED": 0, "CANCELLED": 0}
            mdurs = []
            for t in mtickets:
                m_counts[t.status] = m_counts.get(t.status, 0) + 1
                if t.completed_at and t.created_at:
                    mdurs.append((to_utc(t.completed_at) - to_utc(t.created_at)).total_seconds())
            masters_data.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "total": len(mtickets),
                    "counts": m_counts,
                    "avg_close_sec": (sum(mdurs) / len(mdurs)) if mdurs else None,
                    "median_close_sec": (median(mdurs) if mdurs else None),
                }
            )
            return jsonify(
                {
                    "overall": overall,
                    "masters": masters_data,
                    "total_tickets": total_tickets,
                    "response_sla_breached_count": resp_breach_count,
                    "completion_sla_breached_count": comp_breach_count,
                    "response_sla_breach_percent": (resp_breach_count / total_tickets * 100) if total_tickets else 0,
                    "completion_sla_breach_percent": (comp_breach_count / total_tickets * 100) if total_tickets else 0,
                    "tickets_by_close_reason": reason_counts,
                    "sla_breaches_by_reason": sla_breaches_by_reason,
                    "tickets_by_priority": priority_counts,
                }
            )


@bp.get("/api/archive")
@login_required
@role_required("admin", "dispatcher")
def download_archive():
    from openpyxl import Workbook

    archive_path = config.ARCHIVE_PATH
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "id",
            "object_name",
            "address",
            "lat",
            "lon",
            "description",
            "priority",
            "email",
            "status",
            "close_reason",
            "close_comment",
            "assigned_master_id",
            "assigned_master_name",
            "created_at",
            "updated_at",
            "arrived_at",
            "completed_at",
            "archived_at",
            "custom_sla_response_minutes",
            "custom_sla_completion_minutes",
            "sla_response_breached",
            "sla_completion_breached",
        ]
    )
    with SessionLocal() as db:
        tickets = db.query(Ticket).order_by(Ticket.id).all()
        for t in tickets:
            sla = repository.compute_sla_fields(t)
            ws.append(
                [
                    t.id,
                    t.object_name,
                    t.address,
                    t.lat,
                    t.lon,
                    t.description,
                    t.priority or "MEDIUM",
                    t.email,
                    t.status,
                    t.close_reason,
                    t.close_comment,
                    t.assigned_master_id,
                    t.assigned_master.name if t.assigned_master else None,
                    t.created_at.isoformat() if t.created_at else None,
                    t.updated_at.isoformat() if t.updated_at else None,
                    t.arrived_at.isoformat() if t.arrived_at else None,
                    t.completed_at.isoformat() if t.completed_at else None,
                    t.archived_at.isoformat() if t.archived_at else None,
                    t.custom_sla_response_minutes,
                    t.custom_sla_completion_minutes,
                    sla.get("sla_response_breached"),
                    sla.get("sla_completion_breached"),
                ]
            )
    try:
        wb.save(archive_path)
    except Exception as e:
        print("Failed to save export:", e)
    return send_from_directory(
        directory=os.path.dirname(archive_path),
        path=os.path.basename(archive_path),
        as_attachment=True,
        download_name=os.path.basename(archive_path),
    )
