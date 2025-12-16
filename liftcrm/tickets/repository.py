from sqlalchemy import func  # re-exported for service usage

from ..db import Ticket
from ..utils.time import to_utc
from datetime import datetime, timezone


def serialize_ticket(t: Ticket):
    return {
        "id": t.id,
        "object_name": t.object_name,
        "address": t.address,
        "lat": t.lat,
        "lon": t.lon,
        "description": t.description,
        "email": t.email,
        "status": t.status,
        "assigned_master_id": t.assigned_master_id,
        "assigned_master_name": t.assigned_master.name if t.assigned_master else None,
        "created_at": (to_utc(t.created_at).isoformat() if t.created_at else None),
        "updated_at": (to_utc(t.updated_at).isoformat() if t.updated_at else None),
        "arrived_at": (to_utc(t.arrived_at).isoformat() if t.arrived_at else None),
        "completed_at": (to_utc(t.completed_at).isoformat() if t.completed_at else None),
        "archived_at": (to_utc(t.archived_at).isoformat() if t.archived_at else None),
        "attachments": [
            {"id": a.id, "url": f"/uploads/{a.filename}", "name": a.orig_name} for a in t.attachments
        ],
        "created_ts": (int(to_utc(t.created_at).timestamp() * 1000) if t.created_at else None),
        "elapsed_ms": (
            int(((datetime.now(timezone.utc) - to_utc(t.created_at)).total_seconds()) * 1000) if t.created_at else 0
        ),
    }
