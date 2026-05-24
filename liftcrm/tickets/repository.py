from sqlalchemy import func  # re-exported for service usage

from datetime import datetime, timedelta, timezone

from .. import config
from ..db import Ticket
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
    lat = t.lat
    lon = t.lon
    if (lat is None or lon is None) and t.asset:
        lat = lat if lat is not None else t.asset.lat
        lon = lon if lon is not None else t.asset.lon
    return {
        "id": t.id,
        "object_name": t.object_name,
        "address": t.address,
        "lat": lat,
        "lon": lon,
        "lng": lon,
        "description": t.description,
        "priority": t.priority or "MEDIUM",
        "email": t.email,
        "status": t.status,
        "version": t.version or 1,
        "asset_id": t.asset_id,
        "maintenance_plan_id": t.maintenance_plan_id,
        "maintenance_due_date": t.maintenance_due_date.isoformat() if t.maintenance_due_date else None,
        "asset_serial_no": (t.asset.serial_no if t.asset else None),
        "asset_lift_label": (t.asset.lift_label if t.asset else None),
        "asset_entrance": (t.asset.entrance if t.asset else None),
        "asset_address": (t.asset.address if t.asset else None),
        "customer_id": (t.asset.customer_id if t.asset else None),
        "customer_name": (t.asset.customer.name if t.asset and t.asset.customer else None),
        "contract_id": (t.asset.contract_id if t.asset else None),
        "contract_number": (t.asset.contract.contract_number if t.asset and t.asset.contract else None),
        "contract_title": (t.asset.contract.title if t.asset and t.asset.contract else None),
        "contract_status": (t.asset.contract.status if t.asset and t.asset.contract else None),
        "assigned_master_id": t.assigned_master_id,
        "assigned_master_name": t.assigned_master.name if t.assigned_master else None,
        "created_at": (to_utc(t.created_at).isoformat() if t.created_at else None),
        "assigned_at": (to_utc(t.assigned_at).isoformat() if t.assigned_at else None),
        "updated_at": (to_utc(t.updated_at).isoformat() if t.updated_at else None),
        "accepted_at": (to_utc(t.accepted_at).isoformat() if t.accepted_at else None),
        "arrived_at": (to_utc(t.arrived_at).isoformat() if t.arrived_at else None),
        "waiting_at": (to_utc(t.waiting_at).isoformat() if t.waiting_at else None),
        "waiting_reason": t.waiting_reason,
        "completed_at": (to_utc(t.completed_at).isoformat() if t.completed_at else None),
        "cancelled_at": (to_utc(t.cancelled_at).isoformat() if t.cancelled_at else None),
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
