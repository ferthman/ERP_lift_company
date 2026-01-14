import logging
from flask import Blueprint, jsonify
from flask_login import login_required

from ..db import SessionLocal, Asset
from ..assets.routes import serialize_asset

bp = Blueprint("objects", __name__)
logger = logging.getLogger(__name__)


@bp.get("/api/objects")
@login_required
def api_objects():
    logger.warning("Deprecated /api/objects called; use /api/assets instead.")
    with SessionLocal() as db:
        assets = db.query(Asset).order_by(Asset.id.desc()).all()
        return jsonify([serialize_asset(a) for a in assets])
