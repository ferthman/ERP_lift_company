from flask import Blueprint, jsonify
from flask_login import login_required

from ..db import Asset, SessionLocal
from ..assets.service import asset_display_label

bp = Blueprint("objects", __name__)


@bp.get("/api/objects")
@login_required
def api_objects():
    with SessionLocal() as db:
        assets = (
            db.query(Asset)
            .filter(Asset.status == "ACTIVE")
            .filter(Asset.lat.isnot(None))
            .filter(Asset.lon.isnot(None))
            .order_by(Asset.id)
            .all()
        )
        records = [
            {
                "object_name": asset_display_label(asset),
                "address": asset.address,
                "lat": asset.lat,
                "lon": asset.lon,
            }
            for asset in assets
        ]
        return jsonify(records)
