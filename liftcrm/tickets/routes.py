import logging
import math
import os
import json
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from .service import (
    apply_in_progress_arrival,
    auto_assign_master,
    bump_ticket_version,
    GEOFENCE_RADIUS_M,
    haversine_distance_m,
    is_within_radius,
    send_report,
    validate_status_transition,
)
from . import repository
from ..db import SessionLocal, Master, Ticket, Attachment, User, AuditLog, Asset, AppliedEvent, TicketComment
from ..assets.service import upsert_asset_from_ticket, rounded_coords
from ..utils.security import role_required, generate_temp_password
from ..utils.roles import normalize_role, is_technician
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

PRIORITY_VALUES = ["EMERGENCY", "HIGH", "MEDIUM", "LOW"]
PRIORITY_ALIASES = {
    "EMERGENCY": "EMERGENCY",
    "URGENT": "EMERGENCY",
    "TRAPPED": "EMERGENCY",
    "HIGH": "HIGH",
    "NORMAL": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}
PRIORITY_RANK = {priority: rank for rank, priority in enumerate(PRIORITY_VALUES)}
PRIORITY_SLA_DEFAULTS = {
    "EMERGENCY": {"response": 5, "completion": 60},
    "HIGH": {"response": 15, "completion": 90},
}
HISTORY_STATUSES = {"COMPLETED", "CANCELLED"}


def _transition_error(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message}}), status


def _normalize_priority(value, default="MEDIUM"):
    raw = default if value in (None, "") else value
    key = str(raw).strip().upper()
    return PRIORITY_ALIASES.get(key)


def _priority_sort_rank(ticket):
    return PRIORITY_RANK.get(ticket.priority or "MEDIUM", PRIORITY_RANK["MEDIUM"])


def _priority_sorted(tickets):
    def sort_key(ticket):
        created = to_utc(ticket.created_at)
        created_ts = created.timestamp() if created else 0
        return (_priority_sort_rank(ticket), -created_ts, -(ticket.id or 0))

    return sorted(tickets, key=sort_key)


def _apply_priority_sla_defaults(ticket):
    defaults = PRIORITY_SLA_DEFAULTS.get(ticket.priority or "MEDIUM")
    if not defaults:
        return
    if ticket.custom_sla_response_minutes is None:
        ticket.custom_sla_response_minutes = defaults["response"]
    if ticket.custom_sla_completion_minutes is None:
        ticket.custom_sla_completion_minutes = defaults["completion"]


@bp.get("/api/masters")
@login_required
def list_masters():
    if hasattr(current_user, "is_active") and not current_user.is_active:
        return jsonify({"error": "Account disabled"}), 403
    with SessionLocal() as db:
        ms = db.query(Master).order_by(Master.id).all()
        return jsonify(
            [
                {
                    "id": m.id,
                    "name": m.name,
                    "phone": m.phone,
                    "is_active": bool(m.is_active),
                    "user_id": m.user.id if m.user else None,
                    "username": m.user.username if m.user else None,
                    "user_role": m.user.role if m.user else None,
                    "user_is_active": bool(getattr(m.user, "is_active", 1)) if m.user else None,
                }
                for m in ms
            ]
        )


@bp.post("/api/masters")
@login_required
@role_required("admin")
def create_master():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    phone = phone if phone else None
    if not name:
        return jsonify({"error": "Name is required"}), 400
    with SessionLocal() as db:
        m = Master(name=name, phone=phone, is_active=1)
        db.add(m)
        db.commit()
        db.refresh(m)
        return jsonify({"id": m.id, "name": m.name, "phone": m.phone}), 201


@bp.post("/api/masters/<int:master_id>/reset_password")
@login_required
@role_required("admin")
def reset_master_password(master_id):
    with SessionLocal() as db:
        m = db.get(Master, master_id)
        if not m:
            return jsonify({"error": "Master not found"}), 404
        user = db.query(User).filter(User.master_id == master_id).first()
        if not user:
            return jsonify({"error": "No linked user"}), 404
        temp_password = generate_temp_password()
        user.password_hash = generate_password_hash(temp_password)
        db.commit()
        return jsonify({"ok": True, "username": user.username, "temp_password": temp_password})


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
        open_statuses = ["NEW", "ASSIGNED", "ACCEPTED", "IN_PROGRESS", "WAITING"]
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
            bump_ticket_version(t)
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
            open_statuses = ["NEW", "ASSIGNED", "ACCEPTED", "IN_PROGRESS", "WAITING"]
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
                bump_ticket_version(t)
                counts[new_id] += 1
            reassigned = len(open_tickets)
        db.commit()
        return jsonify({"ok": True, "is_active": bool(m.is_active), "reassigned": reassigned})


@bp.get("/api/tickets")
@login_required
def list_tickets():
    if hasattr(current_user, "is_active") and not current_user.is_active:
        return jsonify({"error": "Account disabled"}), 403
    include_archived = request.args.get("include_archived") in {"1", "true", "True"}
    unassigned_only = request.args.get("unassigned") in {"1", "true", "True"}
    overdue_only = request.args.get("overdue") in {"1", "true", "True"}
    kanban_view = request.args.get("kanban") in {"1", "true", "True"}
    master_id = request.args.get("master_id")
    priority = request.args.get("priority")
    if priority:
        priority = _normalize_priority(priority, default=None)
        if not priority:
            return jsonify({"error": "Invalid priority"}), 400
    if master_id:
        try:
            master_id = int(master_id)
        except ValueError:
            return jsonify({"error": "Invalid master_id"}), 400
    with SessionLocal() as db:
        query = db.query(Ticket)
        if not include_archived:
            query = query.filter(Ticket.archived_at.is_(None))
        if unassigned_only:
            query = query.filter(Ticket.assigned_master_id.is_(None))
        if is_technician(current_user.role):
            if not current_user.master_id:
                return jsonify({"error": "Missing master profile for technician"}), 403
            query = query.filter(Ticket.assigned_master_id == current_user.master_id)
        elif master_id:
            query = query.filter(Ticket.assigned_master_id == master_id)
        if priority:
            query = query.filter(Ticket.priority == priority)
        if kanban_view:
            open_statuses = ["NEW", "ASSIGNED", "ACCEPTED", "IN_PROGRESS", "WAITING"]
            closed_statuses = ["COMPLETED", "CANCELLED"]
            tickets = []
            open_tickets = (
                query.filter(Ticket.status.in_(open_statuses)).order_by(Ticket.created_at.desc()).all()
            )
            tickets.extend(_priority_sorted(open_tickets))
            for status in closed_statuses:
                if status == "COMPLETED":
                    closed_query = query.filter(Ticket.status == status).order_by(
                        repository.func.coalesce(Ticket.completed_at, Ticket.updated_at).desc()
                    )
                else:
                    closed_query = query.filter(Ticket.status == status).order_by(
                        repository.func.coalesce(Ticket.cancelled_at, Ticket.updated_at).desc()
                    )
                tickets.extend(closed_query.limit(4).all())
        else:
            tickets = query.order_by(Ticket.created_at.desc()).all()
            tickets = _priority_sorted(tickets)
        if overdue_only:
            filtered = []
            for t in tickets:
                sla = repository.compute_sla_fields(t)
                if sla["sla_response_breached"] or sla["sla_completion_breached"]:
                    filtered.append(t)
            tickets = filtered
        return jsonify([repository.serialize_ticket(t) for t in tickets])


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _ticket_closed_at(ticket: Ticket):
    if ticket.status == "COMPLETED":
        return to_utc(ticket.completed_at or ticket.updated_at)
    if ticket.status == "CANCELLED":
        return to_utc(ticket.cancelled_at or ticket.updated_at)
    return None


def _parse_iso_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_utc(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return to_utc(parsed)
    return None


def _timeline_actor(actor_user_id, current_user_id):
    if actor_user_id and actor_user_id == current_user_id:
        return "me"
    return "other"


def _is_safe_upload_filename(filename):
    if not filename:
        return False
    if filename in {".", ".."}:
        return False
    if "/" in filename or "\\" in filename:
        return False
    return os.path.basename(filename) == filename


def _can_access_upload_attachment(attachment):
    role = normalize_role(current_user.role)
    ticket = attachment.ticket
    if not ticket:
        return False
    if role == "admin":
        return True
    if ticket.archived_at:
        return False
    if role == "dispatcher":
        return True
    if role == "technician":
        return bool(current_user.master_id and ticket.assigned_master_id == current_user.master_id)
    return False


@bp.get("/api/tickets/history")
@login_required
@role_required("admin", "dispatcher")
def tickets_history():
    raw_statuses = request.args.get("statuses") or request.args.get("status") or "COMPLETED,CANCELLED"
    statuses = [s.strip().upper() for s in raw_statuses.split(",") if s.strip()]
    statuses = [s for s in statuses if s in HISTORY_STATUSES]
    if not statuses:
        statuses = sorted(HISTORY_STATUSES)

    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        return jsonify({"error": "Invalid limit"}), 400
    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "Invalid offset"}), 400
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    start_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc) if date_from else None
    end_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc) if date_to else None

    with SessionLocal() as db:
        query = (
            db.query(Ticket)
            .filter(Ticket.status.in_(statuses), Ticket.archived_at.is_(None))
            .order_by(Ticket.updated_at.desc())
        )
        tickets = query.all()

        filtered = []
        for ticket in tickets:
            closed_at = _ticket_closed_at(ticket)
            if not closed_at:
                continue
            if start_dt and closed_at < start_dt:
                continue
            if end_dt and closed_at > end_dt:
                continue
            filtered.append((closed_at, ticket))

        filtered.sort(key=lambda item: item[0], reverse=True)
        sliced = filtered[offset : offset + limit]
        items = []
        for closed_at, ticket in sliced:
            items.append(
                {
                    "id": ticket.id,
                    "object_name": ticket.object_name,
                    "address": ticket.address,
                    "status": ticket.status,
                    "priority": ticket.priority or "MEDIUM",
                    "closed_at": closed_at.isoformat(),
                    "assigned_master_name": ticket.assigned_master.name if ticket.assigned_master else None,
                    "close_reason": ticket.close_reason,
                    "close_comment": ticket.close_comment,
                }
            )
        return jsonify({"items": items, "total": len(filtered), "limit": limit, "offset": offset})


@bp.get("/api/me/tickets")
@login_required
@role_required("technician")
def list_my_tickets():
    include_closed = request.args.get("include_closed") in {"1", "true", "True"}
    if not current_user.master_id:
        return jsonify({"error": "Missing master profile for technician"}), 403
    closed_statuses = {"COMPLETED", "CANCELLED"}
    with SessionLocal() as db:
        query = (
            db.query(Ticket)
            .filter(
                Ticket.assigned_master_id == current_user.master_id,
                Ticket.archived_at.is_(None),
            )
            .order_by(Ticket.created_at.desc())
        )
        if not include_closed:
            query = query.filter(~Ticket.status.in_(closed_statuses))
        tickets = query.all()
        return jsonify([repository.serialize_ticket(t) for t in tickets])


@bp.get("/api/me/history")
@login_required
@role_required("technician")
def list_my_history():
    if not current_user.master_id:
        return jsonify({"error": "Missing master profile for technician"}), 403
    raw_statuses = request.args.get("status") or request.args.get("statuses") or "COMPLETED,CANCELLED"
    statuses = [s.strip().upper() for s in raw_statuses.split(",") if s.strip()]
    statuses = [s for s in statuses if s in HISTORY_STATUSES]
    if not statuses:
        statuses = sorted(HISTORY_STATUSES)

    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))

    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        return jsonify({"error": "Invalid limit"}), 400
    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "Invalid offset"}), 400
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    start_dt = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc) if date_from else None
    end_dt = datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc) if date_to else None

    with SessionLocal() as db:
        tickets = (
            db.query(Ticket)
            .filter(
                Ticket.assigned_master_id == current_user.master_id,
                Ticket.status.in_(statuses),
                Ticket.archived_at.is_(None),
            )
            .all()
        )
        filtered = []
        for ticket in tickets:
            closed_at = _ticket_closed_at(ticket)
            if not closed_at:
                continue
            if start_dt and closed_at < start_dt:
                continue
            if end_dt and closed_at > end_dt:
                continue
            filtered.append((closed_at, ticket))

        filtered.sort(key=lambda item: item[0], reverse=True)
        sliced = filtered[offset : offset + limit]
        items = []
        for closed_at, ticket in sliced:
            items.append(
                {
                    "ticket_id": ticket.id,
                    "title": ticket.object_name,
                    "object_name": ticket.object_name,
                    "address": ticket.address,
                    "status": ticket.status,
                    "priority": ticket.priority or "MEDIUM",
                    "closed_at": closed_at.isoformat(),
                    "updated_at": (to_utc(ticket.updated_at).isoformat() if ticket.updated_at else None),
                }
            )
        return jsonify({"items": items, "total": len(filtered), "limit": limit, "offset": offset})


@bp.get("/api/me/tickets/<int:ticket_id>/timeline")
@login_required
@role_required("technician")
def ticket_timeline(ticket_id):
    if not current_user.master_id:
        return jsonify({"error": "Missing master profile for technician"}), 403
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return jsonify({"error": "Ticket not found"}), 404
        if ticket.assigned_master_id != current_user.master_id:
            return jsonify({"error": "Forbidden"}), 403
        audit_rows = (
            db.query(AuditLog)
            .filter(AuditLog.entity_type == "ticket", AuditLog.entity_id == ticket_id)
            .order_by(AuditLog.created_at.asc())
            .all()
        )
        comments = (
            db.query(TicketComment)
            .filter(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at.asc())
            .all()
        )
        attachments = (
            db.query(Attachment)
            .filter(Attachment.ticket_id == ticket_id)
            .order_by(Attachment.created_at.asc())
            .all()
        )
        attachment_ids = [a.id for a in attachments]
        attachment_audits = {}
        if attachment_ids:
            attachment_rows = (
                db.query(AuditLog)
                .filter(
                    AuditLog.entity_type == "attachment",
                    AuditLog.entity_id.in_(attachment_ids),
                    AuditLog.action == "CREATE",
                )
                .all()
            )
            attachment_audits = {row.entity_id: row.actor_user_id for row in attachment_rows}

        events = []

        def add_event(ts, payload):
            if ts is None:
                return
            events.append((ts, payload))

        for entry in audit_rows:
            ts = _parse_iso_ts(entry.created_at)
            if not ts:
                continue
            try:
                diff = json.loads(entry.diff_json or "{}")
            except json.JSONDecodeError:
                diff = {}
            old = diff.get("old") or {}
            new = diff.get("new") or {}
            new_status = None
            if entry.action == "CANCEL":
                new_status = "CANCELLED"
            elif entry.action in {"STATUS_CHANGE", "ASSIGN", "CREATE"}:
                new_status = new.get("status")
            if new_status:
                add_event(
                    ts,
                    {
                        "type": "STATUS",
                        "status": new_status,
                        "created_at": ts.isoformat(),
                        "actor": _timeline_actor(entry.actor_user_id, current_user.id),
                        "meta": {"old_status": old.get("status"), "action": entry.action},
                    },
                )

        for comment in comments:
            ts = _parse_iso_ts(comment.created_at)
            add_event(
                ts,
                {
                    "type": "COMMENT",
                    "body": comment.body,
                    "created_at": ts.isoformat() if ts else None,
                    "actor": _timeline_actor(comment.user_id, current_user.id),
                },
            )

        for attachment in attachments:
            ts = _parse_iso_ts(attachment.created_at)
            add_event(
                ts,
                {
                    "type": "PHOTO",
                    "created_at": ts.isoformat() if ts else None,
                    "actor": _timeline_actor(attachment_audits.get(attachment.id), current_user.id),
                    "url": f"/uploads/{attachment.filename}",
                },
            )

        events.sort(key=lambda item: item[0])
        return jsonify([payload for _, payload in events])


@bp.post("/api/tickets")
@login_required
@role_required("admin", "dispatcher")
def create_ticket():
    data = request.get_json() or {}
    asset_id = data.get("asset_id")
    if asset_id is not None:
        try:
            asset_id = int(asset_id)
        except Exception:
            return jsonify({"error": "Invalid asset_id"}), 400
    if "object_name" not in data and not asset_id:
        return jsonify({"error": "Missing field: object_name"}), 400
    priority = _normalize_priority(data.get("priority"))
    if not priority:
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
        asset = None
        if asset_id is not None:
            asset = db.get(Asset, asset_id)
            if not asset:
                return jsonify({"error": "Asset not found"}), 404
        object_name = (data.get("object_name") or "").strip()
        if not object_name and asset:
            object_name = (asset.lift_label or asset.serial_no or asset.address or "Лифт")
        address = data.get("address")
        if not address and asset:
            address = asset.address
        lat = data.get("lat")
        lon = data.get("lon")
        if (lat is None or lon is None) and asset and asset.lat is not None and asset.lon is not None:
            lat, lon = asset.lat, asset.lon
        if lat is None or lon is None:
            return jsonify({"error": "Missing field: lat/lon"}), 400
        lat = float(lat)
        lon = float(lon)
        if asset and (asset.lat is None or asset.lon is None) and rounded_coords(lat, lon)[0] is not None:
            asset.lat = asset.lat if asset.lat is not None else lat
            asset.lon = asset.lon if asset.lon is not None else lon
        t = Ticket(
            object_name=object_name,
            address=address,
            lat=lat,
            lon=lon,
            description=data.get("description"),
            priority=priority,
            email=data.get("email"),
            status="NEW",
            custom_sla_response_minutes=custom_resp,
            custom_sla_completion_minutes=custom_comp,
            asset_id=asset.id if asset else None,
        )
        _apply_priority_sla_defaults(t)
        if not asset and address:
            asset = upsert_asset_from_ticket(db, object_name, address, lat, lon)
            if asset:
                t.asset_id = asset.id
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
    return (
        jsonify(
            {
                "id": t.id,
                "assigned_master_id": t.assigned_master_id,
                "status": t.status,
                "priority": t.priority or "MEDIUM",
                "custom_sla_response_minutes": t.custom_sla_response_minutes,
                "custom_sla_completion_minutes": t.custom_sla_completion_minutes,
            }
        ),
        201,
    )


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
        priority = _normalize_priority(priority, default=None)
        if not priority:
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
        if priority is not None and "custom_sla_response_minutes" not in data and "custom_sla_completion_minutes" not in data:
            _apply_priority_sla_defaults(t)
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
            bump_ticket_version(t)
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
        bump_ticket_version(t)
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
        old_cancelled_at = t.cancelled_at
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
        if t.cancelled_at is None:
            t.cancelled_at = datetime.now(timezone.utc)
        old, new = changed_fields(
            {
                "status": old_status,
                "close_reason": old_reason,
                "close_comment": old_comment,
                "cancelled_at": old_cancelled_at,
            },
            t,
            ["status", "close_reason", "close_comment", "cancelled_at"],
        )
        if old or new:
            bump_ticket_version(t)
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
    if hasattr(current_user, "is_active") and not current_user.is_active:
        return jsonify({"error": "Account disabled"}), 403
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if is_technician(current_user.role):
            if not current_user.master_id:
                return jsonify({"error": "Missing master profile for technician"}), 403
            if t.assigned_master_id != current_user.master_id:
                return jsonify({"error": "Forbidden"}), 403
        payload = repository.serialize_ticket(t)
        payload["comments"] = [
            {
                "id": c.id,
                "user_id": c.user_id,
                "body": c.body,
                "created_at": (to_utc(c.created_at).isoformat() if c.created_at else None),
            }
            for c in (t.comments or [])
        ]
        return jsonify(payload)


@bp.post("/api/sync/events")
@login_required
@role_required("technician")
def sync_events():
    data = request.get_json() or {}
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list):
        return jsonify({"error": {"code": "INVALID_PAYLOAD", "message": "events list is required"}}), 400
    if not current_user.master_id:
        return jsonify({"error": {"code": "MISSING_MASTER", "message": "Missing master profile"}}), 403
    results = []
    with SessionLocal() as db:
        def event_result(event_id, ok, code, message=None, **extra):
            result = {"id": event_id, "ok": ok, "code": code}
            if message:
                result["message"] = message
            result.update(extra)
            return result

        def parse_coord_pair(lat, lon):
            try:
                lat_value = float(lat)
                lon_value = float(lon)
            except (TypeError, ValueError):
                return None
            if not (math.isfinite(lat_value) and math.isfinite(lon_value)):
                return None
            if not (-90 <= lat_value <= 90 and -180 <= lon_value <= 180):
                return None
            return lat_value, lon_value

        def resolve_target_coords(ticket):
            pair = parse_coord_pair(ticket.lat, ticket.lon)
            if pair and not (pair[0] == 0 and pair[1] == 0):
                return pair
            if ticket.asset:
                pair = parse_coord_pair(ticket.asset.lat, ticket.asset.lon)
                if pair and not (pair[0] == 0 and pair[1] == 0):
                    return pair
            return None, None

        for event in events:
            event_id = (event or {}).get("id")
            event_type = (event or {}).get("type")
            ticket_id = (event or {}).get("ticket_id")
            expected_version = (event or {}).get("expected_version")
            payload = (event or {}).get("payload") or {}
            if not event_id or not event_type or not ticket_id or expected_version is None:
                results.append(
                    event_result(
                        event_id,
                        False,
                        "INVALID_EVENT",
                        "Missing required event fields",
                    )
                )
                continue
            existing = db.query(AppliedEvent).filter(AppliedEvent.event_id == event_id).first()
            if existing:
                ticket = db.get(Ticket, ticket_id)
                results.append(
                    event_result(
                        event_id,
                        True,
                        "OK",
                        status="duplicate",
                        ticket={
                            "id": ticket.id if ticket else ticket_id,
                            "status": ticket.status if ticket else None,
                            "version": ticket.version if ticket else None,
                            "priority": ticket.priority if ticket else None,
                        },
                    )
                )
                continue
            ticket = db.get(Ticket, ticket_id)
            if not ticket:
                results.append(event_result(event_id, False, "NOT_FOUND", "Ticket not found"))
                continue
            if ticket.archived_at:
                results.append(event_result(event_id, False, "ARCHIVED", "Ticket archived"))
                continue
            if ticket.assigned_master_id != current_user.master_id:
                results.append(event_result(event_id, False, "FORBIDDEN", "Ticket not assigned to you"))
                continue
            if ticket.version != expected_version:
                results.append(
                    event_result(
                        event_id,
                        False,
                        "CONFLICT",
                        "Ticket version mismatch",
                        server_version=ticket.version,
                        server_status=ticket.status,
                    )
                )
                continue
            if ticket.status in {"COMPLETED", "CANCELLED"} and event_type != "TICKET_ADD_COMMENT":
                results.append(event_result(event_id, False, "IMMUTABLE", "Ticket is closed"))
                continue
            try:
                old_status = ticket.status
                if event_type == "TICKET_ACCEPT":
                    old_accept = ticket.accepted_at
                    ticket.accepted_at = datetime.now(timezone.utc)
                    ticket.status = "ACCEPTED"
                    ok, code, message = validate_status_transition(
                        old_status,
                        ticket.status,
                        ticket,
                        current_user.role,
                        payload,
                    )
                    if not ok:
                        results.append(event_result(event_id, False, code, message))
                        db.rollback()
                        continue
                    old, new = changed_fields(
                        {"status": old_status, "accepted_at": old_accept},
                        ticket,
                        ["status", "accepted_at"],
                    )
                    if old or new:
                        bump_ticket_version(ticket)
                        log_audit(
                            db,
                            entity_type="ticket",
                            entity_id=ticket.id,
                            action="STATUS_CHANGE",
                            actor_user_id=current_user.id,
                            old=old,
                            new=new,
                        )
                elif event_type == "TICKET_IN_PROGRESS":
                    if old_status == "ACCEPTED":
                        tech_lat = payload.get("current_lat")
                        tech_lon = payload.get("current_lng")
                        if tech_lat is None or tech_lon is None:
                            results.append(
                                event_result(
                                    event_id,
                                    False,
                                    "NO_TECH_COORDS",
                                    "Missing technician coordinates",
                                )
                            )
                            db.rollback()
                            continue
                        target_lat, target_lon = resolve_target_coords(ticket)
                        if target_lat is None or target_lon is None:
                            results.append(
                                event_result(
                                    event_id,
                                    False,
                                    "NO_TARGET_COORDS",
                                    "Missing target coordinates",
                                )
                            )
                            db.rollback()
                            continue
                        tech_pair = parse_coord_pair(tech_lat, tech_lon)
                        if not tech_pair:
                            results.append(
                                event_result(
                                    event_id,
                                    False,
                                    "NO_TECH_COORDS",
                                    "Invalid technician coordinates",
                                )
                            )
                            db.rollback()
                            continue
                        tech_lat_value, tech_lon_value = tech_pair
                        distance_m = haversine_distance_m(
                            tech_lat_value,
                            tech_lon_value,
                            target_lat,
                            target_lon,
                        )
                        if not math.isfinite(distance_m):
                            results.append(
                                event_result(
                                    event_id,
                                    False,
                                    "NO_TECH_COORDS",
                                    "Invalid technician coordinates",
                                )
                            )
                            db.rollback()
                            continue
                        if not is_within_radius(
                            tech_lat_value,
                            tech_lon_value,
                            target_lat,
                            target_lon,
                            GEOFENCE_RADIUS_M,
                        ):
                            results.append(
                                event_result(
                                    event_id,
                                    False,
                                    "OUT_OF_RANGE",
                                    "Outside geofence",
                                    distance_m=int(distance_m),
                                    radius_m=GEOFENCE_RADIUS_M,
                                )
                            )
                            db.rollback()
                            continue
                    old_arrived = ticket.arrived_at
                    old_arrival_lat = ticket.arrival_lat
                    old_arrival_lon = ticket.arrival_lon
                    ticket.status = "IN_PROGRESS"
                    if old_status == "WAITING":
                        old_waiting_at = ticket.waiting_at
                        old_waiting_reason = ticket.waiting_reason
                        ticket.waiting_at = None
                        ticket.waiting_reason = None
                        ok, code, message = validate_status_transition(
                            old_status,
                            "IN_PROGRESS",
                            ticket,
                            current_user.role,
                            payload,
                        )
                    else:
                        ok, code, message = validate_status_transition(
                            old_status,
                            ticket.status,
                            ticket,
                            current_user.role,
                            payload,
                        )
                    if not ok:
                        results.append(event_result(event_id, False, code, message))
                        db.rollback()
                        continue
                    apply_in_progress_arrival(ticket, payload)
                    if old_status == "WAITING":
                        old_snapshot = {
                            "status": old_status,
                            "arrived_at": old_arrived,
                            "arrival_lat": old_arrival_lat,
                            "arrival_lon": old_arrival_lon,
                            "waiting_at": old_waiting_at,
                            "waiting_reason": old_waiting_reason,
                        }
                        fields = [
                            "status",
                            "arrived_at",
                            "arrival_lat",
                            "arrival_lon",
                            "waiting_at",
                            "waiting_reason",
                        ]
                    else:
                        old_snapshot = {
                            "status": old_status,
                            "arrived_at": old_arrived,
                            "arrival_lat": old_arrival_lat,
                            "arrival_lon": old_arrival_lon,
                        }
                        fields = ["status", "arrived_at", "arrival_lat", "arrival_lon"]
                    old, new = changed_fields(old_snapshot, ticket, fields)
                    if old or new:
                        bump_ticket_version(ticket)
                        log_audit(
                            db,
                            entity_type="ticket",
                            entity_id=ticket.id,
                            action="STATUS_CHANGE",
                            actor_user_id=current_user.id,
                            old=old,
                            new=new,
                        )
                elif event_type == "TICKET_WAITING":
                    reason = (payload.get("waiting_reason") or "").strip()
                    if not reason:
                        results.append(
                            event_result(
                                event_id,
                                False,
                                "VALIDATION_ERROR",
                                "waiting_reason is required",
                            )
                        )
                        db.rollback()
                        continue
                    old_waiting_at = ticket.waiting_at
                    old_waiting_reason = ticket.waiting_reason
                    ticket.waiting_reason = reason
                    ticket.waiting_at = datetime.now(timezone.utc)
                    ticket.status = "WAITING"
                    ok, code, message = validate_status_transition(
                        old_status,
                        ticket.status,
                        ticket,
                        current_user.role,
                        payload,
                    )
                    if not ok:
                        results.append(event_result(event_id, False, code, message))
                        db.rollback()
                        continue
                    old, new = changed_fields(
                        {"status": old_status, "waiting_reason": old_waiting_reason, "waiting_at": old_waiting_at},
                        ticket,
                        ["status", "waiting_reason", "waiting_at"],
                    )
                    if old or new:
                        bump_ticket_version(ticket)
                        log_audit(
                            db,
                            entity_type="ticket",
                            entity_id=ticket.id,
                            action="STATUS_CHANGE",
                            actor_user_id=current_user.id,
                            old=old,
                            new=new,
                        )
                elif event_type == "TICKET_DONE":
                    close_reason = payload.get("close_reason")
                    close_comment = payload.get("close_comment")
                    if not close_reason:
                        results.append(
                            event_result(
                                event_id,
                                False,
                                "VALIDATION_ERROR",
                                "close_reason is required",
                            )
                        )
                        db.rollback()
                        continue
                    if close_reason not in CLOSE_REASONS:
                        results.append(
                            event_result(
                                event_id,
                                False,
                                "VALIDATION_ERROR",
                                "Invalid close_reason",
                            )
                        )
                        db.rollback()
                        continue
                    old_completed = ticket.completed_at
                    old_reason = ticket.close_reason
                    old_comment = ticket.close_comment
                    ticket.status = "COMPLETED"
                    ticket.completed_at = datetime.now(timezone.utc)
                    ticket.close_reason = close_reason
                    if close_comment is not None:
                        ticket.close_comment = str(close_comment).strip()
                    ok, code, message = validate_status_transition(
                        old_status,
                        ticket.status,
                        ticket,
                        current_user.role,
                        payload,
                    )
                    if not ok:
                        results.append(event_result(event_id, False, code, message))
                        db.rollback()
                        continue
                    old, new = changed_fields(
                        {
                            "status": old_status,
                            "completed_at": old_completed,
                            "close_reason": old_reason,
                            "close_comment": old_comment,
                        },
                        ticket,
                        ["status", "completed_at", "close_reason", "close_comment"],
                    )
                    if old or new:
                        bump_ticket_version(ticket)
                        log_audit(
                            db,
                            entity_type="ticket",
                            entity_id=ticket.id,
                            action="STATUS_CHANGE",
                            actor_user_id=current_user.id,
                            old=old,
                            new=new,
                        )
                elif event_type == "TICKET_ADD_COMMENT":
                    body = (payload.get("body") or "").strip()
                    if not body:
                        results.append(
                            event_result(
                                event_id,
                                False,
                                "VALIDATION_ERROR",
                                "Comment body is required",
                            )
                        )
                        db.rollback()
                        continue
                    comment = TicketComment(ticket_id=ticket.id, user_id=current_user.id, body=body)
                    db.add(comment)
                    db.flush()
                    bump_ticket_version(ticket)
                    log_audit(
                        db,
                        entity_type="ticket_comment",
                        entity_id=comment.id,
                        action="CREATE",
                        actor_user_id=current_user.id,
                        old={},
                        new={"ticket_id": ticket.id, "body": body},
                    )
                else:
                    results.append(
                        event_result(
                            event_id,
                            False,
                            "INVALID_EVENT",
                            "Unknown event type",
                        )
                    )
                    db.rollback()
                    continue
                applied = AppliedEvent(
                    event_id=event_id,
                    user_id=current_user.id,
                    ticket_id=ticket.id,
                )
                db.add(applied)
                db.commit()
                results.append(
                    event_result(
                        event_id,
                        True,
                        "OK",
                        ticket={
                            "id": ticket.id,
                            "status": ticket.status,
                            "version": ticket.version,
                            "priority": ticket.priority or "MEDIUM",
                        },
                    )
                )
            except Exception as exc:
                db.rollback()
                results.append(event_result(event_id, False, "SERVER_ERROR", str(exc)))
    return jsonify({"results": results})


@bp.post("/api/tickets/<int:ticket_id>/arrive")
@login_required
def arrive_ticket(ticket_id):
    if hasattr(current_user, "is_active") and not current_user.is_active:
        return jsonify({"error": "Account disabled"}), 403
    if not is_technician(current_user.role):
        return jsonify({"error": "Only technician can mark arrival"}), 403
    if not current_user.master_id:
        return jsonify({"error": "Missing master profile for technician"}), 403
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
        dist = haversine_distance_m(float(lat), float(lon), t.lat, t.lon)
        if dist > GEOFENCE_RADIUS_M:
            return jsonify({"error": f"Outside geofence ({int(dist)} m > {GEOFENCE_RADIUS_M} m)"}), 403
        old_status = t.status
        old_arrived = t.arrived_at
        old_arrival_lat = t.arrival_lat
        old_arrival_lon = t.arrival_lon
        if old_status == "ASSIGNED":
            t.accepted_at = datetime.now(timezone.utc)
            ok, code, message = validate_status_transition(
                old_status,
                "ACCEPTED",
                t,
                current_user.role,
                {},
            )
            if not ok:
                return _transition_error(code, message)
            old_status = "ACCEPTED"
            t.status = "ACCEPTED"
        t.status = "IN_PROGRESS"
        apply_in_progress_arrival(t, {"lat": lat, "lon": lon})
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
            {
                "status": old_status,
                "arrived_at": old_arrived,
                "arrival_lat": old_arrival_lat,
                "arrival_lon": old_arrival_lon,
            },
            t,
            ["status", "arrived_at", "arrival_lat", "arrival_lon"],
        )
        if old or new:
            bump_ticket_version(t)
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
    if hasattr(current_user, "is_active") and not current_user.is_active:
        return jsonify({"error": "Account disabled"}), 403
    if not is_technician(current_user.role):
        return jsonify({"error": "Only technician can complete"}), 403
    if not current_user.master_id:
        return jsonify({"error": "Missing master profile for technician"}), 403
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
        dist = haversine_distance_m(float(lat), float(lon), t.lat, t.lon)
        if dist > GEOFENCE_RADIUS_M:
            return jsonify({"error": f"Outside geofence ({int(dist)} m > {GEOFENCE_RADIUS_M} m)"}), 403
        old_status = t.status
        old_completed = t.completed_at
        old_reason = t.close_reason
        if old_status == "WAITING":
            ok, code, message = validate_status_transition(
                old_status,
                "IN_PROGRESS",
                t,
                current_user.role,
                {},
            )
            if not ok:
                return _transition_error(code, message)
            old_status = "IN_PROGRESS"
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
            bump_ticket_version(t)
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

    if hasattr(current_user, "is_active") and not current_user.is_active:
        return jsonify({"error": "Account disabled"}), 403
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.archived_at:
            return jsonify({"error": "Ticket archived"}), 400
        if is_technician(current_user.role) and t.assigned_master_id != current_user.master_id:
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
        ticket = db.get(Ticket, ticket_id)
        if ticket:
            bump_ticket_version(ticket)
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
@login_required
def serve_upload(filename):
    if hasattr(current_user, "is_active") and not current_user.is_active:
        abort(403)
    if not _is_safe_upload_filename(filename):
        abort(404)
    with SessionLocal() as db:
        attachment = db.query(Attachment).filter(Attachment.filename == filename).first()
        if not attachment:
            abort(404)
        if not _can_access_upload_attachment(attachment):
            abort(403)
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
        bump_ticket_version(t)
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
    if hasattr(current_user, "is_active") and not current_user.is_active:
        return jsonify({"error": "Account disabled"}), 403
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
        if is_technician(current_user.role):
            if not current_user.master_id:
                return jsonify({"error": "Missing master profile for technician"}), 403
            if t.assigned_master_id != current_user.master_id:
                return jsonify({"error": "Forbidden"}), 403
        elif normalize_role(current_user.role) not in {"admin", "dispatcher"}:
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
        counts = {
            "NEW": 0,
            "ASSIGNED": 0,
            "ACCEPTED": 0,
            "IN_PROGRESS": 0,
            "WAITING": 0,
            "COMPLETED": 0,
            "CANCELLED": 0,
        }
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
            m_counts = {
                "NEW": 0,
                "ASSIGNED": 0,
                "ACCEPTED": 0,
                "IN_PROGRESS": 0,
                "WAITING": 0,
                "COMPLETED": 0,
                "CANCELLED": 0,
            }
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
