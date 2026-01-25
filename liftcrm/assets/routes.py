import csv
import io
import json
import logging
from datetime import datetime, timezone, timedelta, time

from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required

from ..db import SessionLocal, Asset, Ticket, TicketComment, Attachment, AuditLog, User, Master
from ..utils.security import role_required
from ..utils.time import to_utc
from .service import normalize_text

bp = Blueprint("assets", __name__)
logger = logging.getLogger(__name__)


def serialize_asset(asset: Asset):
    return {
        "id": asset.id,
        "address": asset.address,
        "entrance": asset.entrance,
        "lift_label": asset.lift_label,
        "serial_no": asset.serial_no,
        "lat": asset.lat,
        "lon": asset.lon,
        "status": asset.status,
        "created_at": (to_utc(asset.created_at).isoformat() if asset.created_at else None),
        "updated_at": (to_utc(asset.updated_at).isoformat() if asset.updated_at else None),
    }


def _parse_date(value: str, label: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Invalid {label} date format, expected YYYY-MM-DD") from exc


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


def _serialize_actor(user):
    if not user:
        return None
    return {"id": user.id, "username": user.username, "role": user.role}


def _format_status_change(old_status, new_status):
    if old_status or new_status:
        return f"Статус {old_status or '—'} → {new_status or '—'}"
    return "Изменение статуса"


def _format_close_text(reason, comment):
    if reason and comment:
        return f"{reason}: {comment}"
    return reason or comment or "Заявка закрыта"


def _format_iso(dt_value):
    if not dt_value:
        return None
    return to_utc(dt_value).isoformat()


def _first_status_ts(status_events, status):
    for ts, state in status_events:
        if state == status:
            return ts
    return None


def _compute_ticket_metrics(ticket, status_events):
    created_at = to_utc(ticket.created_at) if ticket.created_at else None
    response_ts = None
    if ticket.arrived_at:
        response_ts = to_utc(ticket.arrived_at)
    elif ticket.accepted_at:
        response_ts = to_utc(ticket.accepted_at)
    else:
        response_ts = _first_status_ts(status_events, "IN_PROGRESS")

    response_seconds = None
    if created_at and response_ts and response_ts >= created_at:
        response_seconds = int((response_ts - created_at).total_seconds())

    in_progress_ts = _first_status_ts(status_events, "IN_PROGRESS")
    completed_ts = to_utc(ticket.completed_at) if ticket.completed_at else _first_status_ts(status_events, "COMPLETED")
    repair_seconds = None
    if in_progress_ts and completed_ts and completed_ts >= in_progress_ts:
        repair_seconds = int((completed_ts - in_progress_ts).total_seconds())

    downtime_seconds = None
    waiting_durations = []
    waiting_start = None
    last_ts = None
    for ts, status in status_events:
        last_ts = ts
        if status == "WAITING":
            if waiting_start is None:
                waiting_start = ts
        else:
            if waiting_start is not None:
                waiting_durations.append((ts - waiting_start).total_seconds())
                waiting_start = None
    if waiting_start is not None and last_ts is not None:
        waiting_durations.append((last_ts - waiting_start).total_seconds())
        waiting_start = None
    if waiting_durations:
        downtime_seconds = int(sum(waiting_durations))

    return {
        "response_seconds": response_seconds,
        "repair_seconds": repair_seconds,
        "downtime_seconds": downtime_seconds,
    }


def _ensure_unique_serial(db, serial_no, asset_id=None):
    if not serial_no:
        return None
    q = db.query(Asset).filter(Asset.serial_no == serial_no)
    if asset_id is not None:
        q = q.filter(Asset.id != asset_id)
    return q.first()


@bp.get("/api/assets")
@login_required
def list_assets():
    search = request.args.get("search")
    with SessionLocal() as db:
        assets = db.query(Asset).order_by(Asset.id.desc()).all()
        if search:
            term = normalize_text(search)
            if term:
                filtered = []
                for asset in assets:
                    haystack = normalize_text(
                        f"{asset.address_norm or asset.address or ''} {asset.serial_no or ''} {asset.lift_label or ''} {asset.entrance or ''}"
                    )
                    if term in haystack:
                        filtered.append(asset)
                assets = filtered
        return jsonify([serialize_asset(a) for a in assets])


@bp.post("/api/assets")
@login_required
@role_required("admin", "dispatcher")
def create_asset():
    data = request.get_json() or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"error": "Address is required"}), 400
    serial_no = (data.get("serial_no") or "").strip() or None
    with SessionLocal() as db:
        if serial_no and _ensure_unique_serial(db, serial_no):
            return jsonify({"error": "serial_no must be unique"}), 400
        asset = Asset(
            address=address,
            address_norm=normalize_text(address),
            entrance=(data.get("entrance") or "").strip() or None,
            lift_label=(data.get("lift_label") or "").strip() or None,
            serial_no=serial_no,
            lat=float(data["lat"]) if data.get("lat") not in (None, "") else None,
            lon=float(data["lon"]) if data.get("lon") not in (None, "") else None,
            status=(data.get("status") or "ACTIVE").strip().upper(),
        )
        if asset.status not in {"ACTIVE", "INACTIVE"}:
            return jsonify({"error": "Invalid status"}), 400
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return jsonify(serialize_asset(asset)), 201


@bp.get("/api/assets/<int:asset_id>")
@login_required
@role_required("admin", "dispatcher")
def get_asset(asset_id):
    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        return jsonify(serialize_asset(asset))


@bp.patch("/api/assets/<int:asset_id>")
@login_required
@role_required("admin", "dispatcher")
def update_asset(asset_id):
    data = request.get_json() or {}
    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        if "address" in data:
            address = (data.get("address") or "").strip()
            if not address:
                return jsonify({"error": "Address is required"}), 400
            asset.address = address
            asset.address_norm = normalize_text(address)
        if "entrance" in data:
            asset.entrance = (data.get("entrance") or "").strip() or None
        if "lift_label" in data:
            asset.lift_label = (data.get("lift_label") or "").strip() or None
        if "serial_no" in data:
            serial_no = (data.get("serial_no") or "").strip() or None
            if serial_no and _ensure_unique_serial(db, serial_no, asset_id=asset_id):
                return jsonify({"error": "serial_no must be unique"}), 400
            asset.serial_no = serial_no
        if "lat" in data:
            asset.lat = float(data["lat"]) if data.get("lat") not in (None, "") else None
        if "lon" in data:
            asset.lon = float(data["lon"]) if data.get("lon") not in (None, "") else None
        if "status" in data:
            status = (data.get("status") or "").strip().upper()
            if status not in {"ACTIVE", "INACTIVE"}:
                return jsonify({"error": "Invalid status"}), 400
            asset.status = status
        asset.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(asset)
        return jsonify(serialize_asset(asset))


@bp.delete("/api/assets/<int:asset_id>")
@login_required
@role_required("admin", "dispatcher")
def delete_asset(asset_id):
    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        asset.status = "INACTIVE"
        db.commit()
        return jsonify({"ok": True})


@bp.get("/api/lifts/<int:asset_id>/history")
@login_required
@role_required("admin", "dispatcher")
def lift_history(asset_id):
    q = normalize_text(request.args.get("q") or "")
    from_param = request.args.get("from")
    to_param = request.args.get("to")
    try:
        from_date = _parse_date(from_param, "from")
        to_date = _parse_date(to_param, "to")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now = datetime.now(timezone.utc)
    if from_date is None and to_date is None:
        from_dt = now - timedelta(days=90)
        to_dt = now
    else:
        to_dt = (
            datetime.combine(to_date, time.max).replace(tzinfo=timezone.utc)
            if to_date
            else now
        )
        if from_date:
            from_dt = datetime.combine(from_date, time.min).replace(tzinfo=timezone.utc)
        else:
            from_dt = (to_dt - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)

    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        tickets = db.query(Ticket).filter(Ticket.asset_id == asset_id).all()
        ticket_ids = [t.id for t in tickets]
        audits = []
        comments = []
        attachments = []
        if ticket_ids:
            audits = (
                db.query(AuditLog)
                .filter(AuditLog.entity_type == "ticket", AuditLog.entity_id.in_(ticket_ids))
                .order_by(AuditLog.created_at.desc())
                .all()
            )
            comments = db.query(TicketComment).filter(TicketComment.ticket_id.in_(ticket_ids)).all()
            attachments = db.query(Attachment).filter(Attachment.ticket_id.in_(ticket_ids)).all()

        user_ids = {entry.actor_user_id for entry in audits if entry.actor_user_id}
        user_ids.update({c.user_id for c in comments if c.user_id})
        users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
        users_by_id = {u.id: u for u in users}

        master_ids = {t.assigned_master_id for t in tickets if t.assigned_master_id}
        masters = db.query(Master).filter(Master.id.in_(master_ids)).all() if master_ids else []
        masters_by_id = {m.id: m for m in masters}
        master_users = db.query(User).filter(User.master_id.in_(master_ids)).all() if master_ids else []
        users_by_master_id = {u.master_id: u for u in master_users if u.master_id}

        events_by_ticket = {t.id: [] for t in tickets}
        status_events_by_ticket = {t.id: [] for t in tickets}
        last_ts_by_ticket = {t.id: to_utc(t.created_at) if t.created_at else None for t in tickets}
        ticket_map = {t.id: t for t in tickets}

        def add_event(ts_dt, kind, actor_id, ticket_id, text, meta=None):
            if ts_dt is None:
                return
            ticket_events = events_by_ticket.get(ticket_id)
            if ticket_events is None:
                return
            ticket_events.append(
                {
                    "ts": ts_dt.isoformat(),
                    "kind": kind,
                    "actor": _serialize_actor(users_by_id.get(actor_id)),
                    "text": text,
                    "meta": meta or {},
                }
            )
            last_ts = last_ts_by_ticket.get(ticket_id)
            if last_ts is None or ts_dt > last_ts:
                last_ts_by_ticket[ticket_id] = ts_dt

        for entry in audits:
            ts_dt = _parse_iso_ts(entry.created_at)
            if ts_dt is None:
                continue
            try:
                payload = json.loads(entry.diff_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            old = payload.get("old") or {}
            new = payload.get("new") or {}
            action = entry.action
            text = None
            kind = None
            meta = {"action": action}
            if action == "CREATE":
                kind = "CREATE"
                text = "Создана заявка"
                status_events_by_ticket.get(entry.entity_id, []).append((ts_dt, new.get("status") or "NEW"))
            elif action == "ASSIGN":
                kind = "ASSIGN"
                master_id = new.get("assigned_master_id")
                master = masters_by_id.get(master_id)
                if master:
                    text = f"Назначен мастер: {master.name}"
                else:
                    text = "Назначен мастер"
            elif action == "CANCEL":
                kind = "CLOSE"
                text = _format_close_text(new.get("close_reason"), new.get("close_comment"))
                status_events_by_ticket.get(entry.entity_id, []).append((ts_dt, "CANCELLED"))
            elif action == "STATUS_CHANGE":
                new_status = new.get("status")
                old_status = old.get("status")
                meta.update({"status": new_status, "old_status": old_status})
                if new_status:
                    status_events_by_ticket.get(entry.entity_id, []).append((ts_dt, new_status))
                if new_status == "WAITING" or new.get("waiting_reason"):
                    kind = "WAITING"
                    text = new.get("waiting_reason") or _format_status_change(old_status, new_status)
                elif new_status == "COMPLETED":
                    kind = "CLOSE"
                    text = _format_close_text(new.get("close_reason"), new.get("close_comment"))
                else:
                    kind = "STATUS_CHANGE"
                    text = _format_status_change(old_status, new_status)
            elif action == "EDIT":
                kind = "STATUS_CHANGE"
                changed = ", ".join(new.keys()) if isinstance(new, dict) else ""
                text = f"Обновлены поля: {changed}" if changed else "Обновление заявки"
            if kind:
                add_event(ts_dt, kind, entry.actor_user_id, entry.entity_id, text, meta=meta)

        audited_create = {entry.entity_id for entry in audits if entry.action == "CREATE"}
        for ticket in tickets:
            if ticket.id in audited_create:
                continue
            add_event(
                to_utc(ticket.created_at),
                "CREATE",
                None,
                ticket.id,
                "Создана заявка",
            )

        for comment in comments:
            add_event(
                to_utc(comment.created_at),
                "COMMENT",
                comment.user_id,
                comment.ticket_id,
                comment.body,
            )

        for attachment in attachments:
            add_event(
                to_utc(attachment.created_at),
                "ATTACHMENT",
                None,
                attachment.ticket_id,
                attachment.orig_name,
                meta={"filename": attachment.filename, "id": attachment.id},
            )

        def matches_query(ticket, ticket_events):
            if not q:
                return True
            haystack = normalize_text(
                f"{ticket.object_name or ''} {ticket.description or ''}"
            )
            if q in haystack:
                return True
            for ev in ticket_events:
                if q in normalize_text(ev.get("text") or ""):
                    return True
            return False

        tickets_payload = []
        for ticket in tickets:
            created_at = to_utc(ticket.created_at) if ticket.created_at else None
            if created_at and (created_at < from_dt or created_at > to_dt):
                continue
            ticket_events = events_by_ticket.get(ticket.id, [])
            if not matches_query(ticket, ticket_events):
                continue
            status_events = sorted(
                status_events_by_ticket.get(ticket.id, []),
                key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc),
            )
            metrics = _compute_ticket_metrics(ticket, status_events)
            last_ts = last_ts_by_ticket.get(ticket.id) or created_at
            master = masters_by_id.get(ticket.assigned_master_id)
            master_user = users_by_master_id.get(ticket.assigned_master_id)
            assigned = None
            if master or master_user:
                assigned = {
                    "id": master.id if master else None,
                    "name": master.name if master else None,
                    "username": master_user.username if master_user else None,
                }
            ticket_events_sorted = sorted(
                ticket_events,
                key=lambda x: x["ts"],
                reverse=True,
            )
            tickets_payload.append(
                {
                    "ticket": {
                        "id": ticket.id,
                        "title": ticket.object_name,
                        "description": ticket.description,
                        "status": ticket.status,
                        "created_at": _format_iso(ticket.created_at),
                        "completed_at": _format_iso(ticket.completed_at),
                        "accepted_at": _format_iso(ticket.accepted_at),
                        "arrived_at": _format_iso(ticket.arrived_at),
                        "waiting_at": _format_iso(ticket.waiting_at),
                        "waiting_reason": ticket.waiting_reason,
                        "assigned": assigned,
                    },
                    "events": ticket_events_sorted,
                    "summary": {
                        "last_ts": last_ts.isoformat() if last_ts else None,
                        "events_count": len(ticket_events_sorted),
                        "metrics": metrics,
                    },
                }
            )

        tickets_payload.sort(
            key=lambda entry: entry["summary"]["last_ts"] or "",
            reverse=True,
        )

        return jsonify({"lift": serialize_asset(asset), "tickets": tickets_payload})


@bp.get("/api/assets/export.xlsx")
@login_required
@role_required("admin", "dispatcher")
def export_assets_xlsx():
    with SessionLocal() as db:
        rows = db.query(Asset).order_by(Asset.id).all()
    try:
        from openpyxl import Workbook
    except Exception as exc:
        logger.exception("openpyxl missing", exc_info=exc)
        return jsonify({"error": "openpyxl is required"}), 500
    wb = Workbook()
    ws = wb.active
    headers = [
        "id",
        "address",
        "entrance",
        "lift_label",
        "serial_no",
        "lat",
        "lon",
        "status",
        "created_at",
        "updated_at",
    ]
    ws.append(headers)
    for a in rows:
        ws.append(
            [
                a.id,
                a.address,
                a.entrance,
                a.lift_label,
                a.serial_no,
                a.lat,
                a.lon,
                a.status,
                a.created_at.isoformat() if a.created_at else None,
                a.updated_at.isoformat() if a.updated_at else None,
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="assets.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.get("/api/assets/export.csv")
@login_required
@role_required("admin", "dispatcher")
def export_assets_csv():
    with SessionLocal() as db:
        rows = db.query(Asset).order_by(Asset.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "id",
        "address",
        "entrance",
        "lift_label",
        "serial_no",
        "lat",
        "lon",
        "status",
        "created_at",
        "updated_at",
    ]
    writer.writerow(headers)
    for a in rows:
        writer.writerow(
            [
                a.id,
                a.address,
                a.entrance,
                a.lift_label,
                a.serial_no,
                a.lat,
                a.lon,
                a.status,
                a.created_at.isoformat() if a.created_at else None,
                a.updated_at.isoformat() if a.updated_at else None,
            ]
        )
    buf = io.BytesIO(output.getvalue().encode("utf-8"))
    return send_file(
        buf,
        as_attachment=True,
        download_name="assets.csv",
        mimetype="text/csv",
    )
