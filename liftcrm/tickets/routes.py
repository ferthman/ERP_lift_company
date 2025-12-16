import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_from_directory
from flask_login import login_required, current_user

from .service import auto_assign_master, haversine_m, send_report, archive_ticket
from . import repository
from ..db import SessionLocal, Master, Ticket, Attachment, User
from ..utils.security import role_required
from ..utils.time import to_utc
from .. import config

bp = Blueprint("tickets", __name__)

ALLOWED_EXTS = {"png", "jpg", "jpeg", "webp"}


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
        open_tickets = db.query(Ticket).filter(Ticket.assigned_master_id == master_id, Ticket.status.in_(open_statuses)).all()
        counts = {x.id: 0 for x in others}
        rows = (
            db.query(Ticket.assigned_master_id, repository.func.count(Ticket.id))
            .filter(Ticket.status.in_(open_statuses), Ticket.assigned_master_id.in_([x.id for x in others]))
            .group_by(Ticket.assigned_master_id)
            .all()
        )
        for mid, cnt in rows:
            counts[mid] = cnt
        for t in open_tickets:
            new_id = min(counts, key=lambda k: (counts[k], k))
            t.assigned_master_id = new_id
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
            open_tickets = db.query(Ticket).filter(Ticket.assigned_master_id == master_id, Ticket.status.in_(open_statuses)).all()
            counts = {x.id: 0 for x in others}
            rows = (
                db.query(Ticket.assigned_master_id, repository.func.count(Ticket.id))
                .filter(Ticket.status.in_(open_statuses), Ticket.assigned_master_id.in_([x.id for x in others]))
                .group_by(Ticket.assigned_master_id)
                .all()
            )
            for mid, cnt in rows:
                counts[mid] = cnt
            for t in open_tickets:
                new_id = min(counts, key=lambda k: (counts[k], k))
                t.assigned_master_id = new_id
                if t.status in ["NEW", "ASSIGNED"]:
                    t.status = "ASSIGNED"
                counts[new_id] += 1
            reassigned = len(open_tickets)
        db.commit()
        return jsonify({"ok": True, "is_active": bool(m.is_active), "reassigned": reassigned})


@bp.get("/api/tickets")
@login_required
def list_tickets():
    with SessionLocal() as db:
        tickets = db.query(Ticket).order_by(Ticket.created_at.desc()).all()
        return jsonify([repository.serialize_ticket(t) for t in tickets])


@bp.post("/api/tickets")
@login_required
@role_required("admin", "dispatcher")
def create_ticket():
    data = request.get_json() or {}
    for k in ("object_name", "lat", "lon"):
        if k not in data:
            return jsonify({"error": f"Missing field: {k}"}), 400
    with SessionLocal() as db:
        t = Ticket(
            object_name=data["object_name"],
            address=data.get("address"),
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            description=data.get("description"),
            email=data.get("email"),
            status="NEW",
        )
        m = auto_assign_master(db)
        if m:
            t.assigned_master_id, t.status = m.id, "ASSIGNED"
        db.add(t)
        db.commit()
        return jsonify({"id": t.id, "assigned_master_id": t.assigned_master_id, "status": t.status}), 201


@bp.post("/api/tickets/<int:ticket_id>/reassign")
@login_required
@role_required("admin", "dispatcher")
def reassign_ticket(ticket_id):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        m = auto_assign_master(db)
        if not m:
            return jsonify({"error": "No active masters available"}), 400
        t.assigned_master_id = m.id
        if t.status in ["NEW", "ASSIGNED"]:
            t.status = "ASSIGNED"
        db.commit()
        return jsonify({"message": "Reassigned", "assigned_master_id": t.assigned_master_id})


@bp.post("/api/tickets/<int:ticket_id>/cancel")
@login_required
@role_required("admin", "dispatcher")
def cancel_ticket(ticket_id):
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.status in ["COMPLETED", "CANCELLED"]:
            return jsonify({"error": "Ticket already finalized"}), 400
        t.status = "CANCELLED"
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
        if t.assigned_master_id != current_user.master_id:
            return jsonify({"error": "Ticket not assigned to you"}), 403
        if lat is None or lon is None:
            return jsonify({"error": "lat/lon required"}), 400
        dist = haversine_m(float(lat), float(lon), t.lat, t.lon)
        if dist > 500:
            return jsonify({"error": f"Outside geofence ({int(dist)} m > 500 m)"}), 403
        t.status = "IN_PROGRESS"
        t.arrived_at = datetime.now(timezone.utc)
        t.arrival_lat = float(lat)
        t.arrival_lon = float(lon)
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
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        if t.assigned_master_id != current_user.master_id:
            return jsonify({"error": "Ticket not assigned to you"}), 403
        if lat is None or lon is None:
            return jsonify({"error": "lat/lon required"}), 400
        dist = haversine_m(float(lat), float(lon), t.lat, t.lon)
        if dist > 500:
            return jsonify({"error": f"Outside geofence ({int(dist)} m > 500 m)"}), 403
        t.status = "COMPLETED"
        t.completed_at = datetime.now(timezone.utc)
        t.completion_lat = float(lat)
        t.completion_lon = float(lon)
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
        m = db.get(Master, master_id)
        if not m:
            return jsonify({"error": "Master not found"}), 404
        if int(getattr(m, "is_active", 1)) != 1:
            return jsonify({"error": "Мастер неактивен"}), 400
        t.assigned_master_id = m.id
        if t.status in ["NEW", "ASSIGNED"]:
            t.status = "ASSIGNED"
        db.commit()
        return jsonify({"message": "Assigned", "assigned_master_id": t.assigned_master_id, "assigned_master_name": m.name})


@bp.delete("/api/tickets/<int:ticket_id>")
@login_required
@role_required("admin", "dispatcher")
def delete_ticket(ticket_id):
    from flask import current_app

    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if not t:
            return jsonify({"error": "Ticket not found"}), 404
        try:
            archive_ticket(t, config.ARCHIVE_PATH)
        except Exception as e:
            print("Archive failed:", e)
        for a in list(t.attachments):
            try:
                os.remove(os.path.join(current_app.config["UPLOAD_FOLDER"], a.filename))
            except Exception:
                pass
        db.delete(t)
        db.commit()
        return jsonify({"message": "Deleted"})


@bp.get("/api/metrics")
@login_required
@role_required("admin", "dispatcher")
def metrics():
    from statistics import median

    with SessionLocal() as db:
        tickets = db.query(Ticket).all()
        counts = {"NEW": 0, "ASSIGNED": 0, "IN_PROGRESS": 0, "COMPLETED": 0, "CANCELLED": 0}
        for t in tickets:
            counts[t.status] = counts.get(t.status, 0) + 1
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
        return jsonify({"overall": overall, "masters": masters_data})


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
            "email",
            "status",
            "assigned_master_id",
            "assigned_master_name",
            "created_at",
            "updated_at",
            "arrived_at",
            "completed_at",
        ]
    )
    with SessionLocal() as db:
        tickets = db.query(Ticket).order_by(Ticket.id).all()
        for t in tickets:
            ws.append(
                [
                    t.id,
                    t.object_name,
                    t.address,
                    t.lat,
                    t.lon,
                    t.description,
                    t.email,
                    t.status,
                    t.assigned_master_id,
                    t.assigned_master.name if t.assigned_master else None,
                    t.created_at.isoformat() if t.created_at else None,
                    t.updated_at.isoformat() if t.updated_at else None,
                    t.arrived_at.isoformat() if t.arrived_at else None,
                    t.completed_at.isoformat() if t.completed_at else None,
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
