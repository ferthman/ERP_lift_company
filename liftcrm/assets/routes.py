import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required
from sqlalchemy import func, or_

from ..db import Asset, SessionLocal
from ..utils.security import role_required
from ..utils.time import to_utc
from .service import normalize_status, serialize_asset

bp = Blueprint("assets", __name__)

STATUS_VALUES = {"ACTIVE", "INACTIVE"}


def _optional_float(value):
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value):
    if value in (None, ""):
        return None
    return int(value)


def _asset_exists(db, serial_no, asset_id=None):
    if not serial_no:
        return False
    query = db.query(Asset).filter(Asset.serial_no == serial_no)
    if asset_id is not None:
        query = query.filter(Asset.id != asset_id)
    return db.query(query.exists()).scalar()


def _asset_rows(db):
    return db.query(Asset).order_by(Asset.id).all()


def _export_payload(asset):
    return [
        asset.id,
        asset.address,
        asset.entrance,
        asset.lift_label,
        asset.serial_no,
        asset.lat,
        asset.lon,
        asset.status,
        (to_utc(asset.created_at).isoformat() if asset.created_at else None),
        (to_utc(asset.updated_at).isoformat() if asset.updated_at else None),
    ]


@bp.get("/api/assets")
@login_required
@role_required("admin", "dispatcher")
def list_assets():
    search = (request.args.get("search") or "").strip()
    with SessionLocal() as db:
        query = db.query(Asset)
        if search:
            term = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(Asset.address).like(term),
                    func.lower(Asset.serial_no).like(term),
                    func.lower(Asset.lift_label).like(term),
                    func.lower(Asset.entrance).like(term),
                )
            )
        assets = query.order_by(Asset.id).all()
        return jsonify([serialize_asset(a) for a in assets])


@bp.post("/api/assets")
@login_required
@role_required("admin", "dispatcher")
def create_asset():
    data = request.get_json() or {}
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"error": "Missing field: address"}), 400
    serial_no = (data.get("serial_no") or "").strip() or None
    status = normalize_status(data.get("status"))
    if status not in STATUS_VALUES:
        return jsonify({"error": "Invalid status"}), 400

    with SessionLocal() as db:
        if _asset_exists(db, serial_no):
            return jsonify({"error": "serial_no already exists"}), 409
        asset = Asset(
            address=address,
            entrance=(data.get("entrance") or "").strip() or None,
            lift_label=(data.get("lift_label") or "").strip() or None,
            serial_no=serial_no,
            customer_id=_optional_int(data.get("customer_id")),
            lat=_optional_float(data.get("lat")),
            lon=_optional_float(data.get("lon")),
            status=status,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
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

        updates = {}
        if "address" in data:
            updates["address"] = (data.get("address") or "").strip()
            if not updates["address"]:
                return jsonify({"error": "Missing field: address"}), 400
        if "entrance" in data:
            updates["entrance"] = (data.get("entrance") or "").strip() or None
        if "lift_label" in data:
            updates["lift_label"] = (data.get("lift_label") or "").strip() or None
        if "serial_no" in data:
            serial_no = (data.get("serial_no") or "").strip() or None
            if _asset_exists(db, serial_no, asset_id=asset.id):
                return jsonify({"error": "serial_no already exists"}), 409
            updates["serial_no"] = serial_no
        if "customer_id" in data:
            updates["customer_id"] = _optional_int(data.get("customer_id"))
        if "lat" in data:
            updates["lat"] = _optional_float(data.get("lat"))
        if "lon" in data:
            updates["lon"] = _optional_float(data.get("lon"))
        if "status" in data:
            status = normalize_status(data.get("status"))
            if status not in STATUS_VALUES:
                return jsonify({"error": "Invalid status"}), 400
            updates["status"] = status

        if not updates:
            return jsonify({"error": "No fields to update"}), 400

        for key, value in updates.items():
            setattr(asset, key, value)
        asset.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(asset)
        return jsonify(serialize_asset(asset))


@bp.delete("/api/assets/<int:asset_id>")
@login_required
@role_required("admin", "dispatcher")
def deactivate_asset(asset_id):
    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        asset.status = "INACTIVE"
        asset.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(asset)
        return jsonify(serialize_asset(asset))


@bp.get("/api/assets/export.csv")
@login_required
@role_required("admin", "dispatcher")
def export_assets_csv():
    with SessionLocal() as db:
        assets = _asset_rows(db)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
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
        )
        for asset in assets:
            writer.writerow(_export_payload(asset))
        data = io.BytesIO(output.getvalue().encode("utf-8"))
        return send_file(data, mimetype="text/csv", as_attachment=True, download_name="assets.csv")


@bp.get("/api/assets/export.xlsx")
@login_required
@role_required("admin", "dispatcher")
def export_assets_xlsx():
    with SessionLocal() as db:
        assets = _asset_rows(db)
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(
            [
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
        )
        for asset in assets:
            ws.append(_export_payload(asset))
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="assets.xlsx",
        )
