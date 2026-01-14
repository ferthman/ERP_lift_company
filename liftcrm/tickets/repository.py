from sqlalchemy import func  # re-exported for service usage

from datetime import datetime, timedelta, timezone

from .. import config
from ..db import Ticket
from ..assets.service import build_asset_summary
from ..utils.time import to_utc


def compute_sla_fields(t: Ticket):
    created = to_utc(t.created_at)
    now = datetime.now(timezone.utc)
    if not created:
        return {
            "sla_response_deadline": None,
            "sla_completion_deadline": None,
            "sla_response_breached": False,
            "sla_completion_breached": False,
            "sla_response_minutes_left": None,
            "sla_completion_minutes_left": None,
        }

    response_minutes = t.custom_sla_response_minutes or config.SLA_RESPONSE_MINUTES
    completion_minutes = t.custom_sla_completion_minutes or config.SLA_COMPLETION_MINUTES

    response_deadline = created + timedelta(minutes=response_minutes)
    completion_deadline = created + timedelta(minutes=completion_minutes)

    arrived = to_utc(t.arrived_at)
    completed = to_utc(t.completed_at)

    response_elapsed_end = arrived or now
    completion_elapsed_end = completed or now

    response_elapsed_minutes = int((response_elapsed_end - created).total_seconds() // 60)
    completion_elapsed_minutes = int((completion_elapsed_end - created).total_seconds() // 60)

    response_breached = response_elapsed_minutes > response_minutes
    completion_breached = completion_elapsed_minutes > completion_minutes

    response_left = response_minutes - response_elapsed_minutes
    completion_left = completion_minutes - completion_elapsed_minutes

    return {
        "sla_response_deadline": response_deadline.isoformat(),
        "sla_completion_deadline": completion_deadline.isoformat(),
        "sla_response_breached": bool(response_breached),
        "sla_completion_breached": bool(completion_breached),
        "sla_response_minutes_left": response_left,
        "sla_completion_minutes_left": completion_left,
    }


def serialize_ticket(t: Ticket):
    sla = compute_sla_fields(t)
    return {
        "id": t.id,
        "object_name": t.object_name,
        "address": t.address,
        "lat": t.lat,
        "lon": t.lon,
        "asset_id": t.asset_id,
        "asset_summary": build_asset_summary(t.asset),
        "description": t.description,
        "priority": t.priority or "MEDIUM",
        "email": t.email,
        "status": t.status,
        "assigned_master_id": t.assigned_master_id,
        "assigned_master_name": t.assigned_master.name if t.assigned_master else None,
        "created_at": (to_utc(t.created_at).isoformat() if t.created_at else None),
        "assigned_at": (to_utc(t.assigned_at).isoformat() if t.assigned_at else None),
        "updated_at": (to_utc(t.updated_at).isoformat() if t.updated_at else None),
        "arrived_at": (to_utc(t.arrived_at).isoformat() if t.arrived_at else None),
        "completed_at": (to_utc(t.completed_at).isoformat() if t.completed_at else None),
        "archived_at": (to_utc(t.archived_at).isoformat() if t.archived_at else None),
        "close_reason": t.close_reason,
        "close_comment": t.close_comment,
        "attachments": [
            {"id": a.id, "url": f"/uploads/{a.filename}", "name": a.orig_name} for a in t.attachments
        ],
        "custom_sla_response_minutes": t.custom_sla_response_minutes,
        "custom_sla_completion_minutes": t.custom_sla_completion_minutes,
        "created_ts": (int(to_utc(t.created_at).timestamp() * 1000) if t.created_at else None),
        "elapsed_ms": (
            int(((datetime.now(timezone.utc) - to_utc(t.created_at)).total_seconds()) * 1000) if t.created_at else 0
        ),
        **sla,
    }
