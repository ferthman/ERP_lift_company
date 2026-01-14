import csv
import io
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required

from ..db import SessionLocal, Asset
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
                        f"{asset.address or ''} {asset.serial_no or ''} {asset.lift_label or ''} {asset.entrance or ''}"
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
