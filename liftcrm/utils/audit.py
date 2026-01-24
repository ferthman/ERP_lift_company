import json
import logging
from datetime import datetime, timezone

from ..db import AuditLog

logger = logging.getLogger(__name__)


def _serialize_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _serialize_payload(payload):
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        return payload
    return {key: _serialize_value(val) for key, val in payload.items()}


def _build_changed(old_payload, new_payload):
    old_data = old_payload or {}
    new_data = new_payload or {}
    changed = {}
    for field in set(old_data.keys()) | set(new_data.keys()):
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        if old_val != new_val:
            changed[field] = {"old": old_val, "new": new_val}
    return changed


def changed_fields(old_obj, new_obj, allowed_fields):
    old_data = {}
    new_data = {}
    for field in allowed_fields:
        if isinstance(old_obj, dict):
            old_val = old_obj.get(field)
        else:
            old_val = getattr(old_obj, field, None) if old_obj is not None else None
        if isinstance(new_obj, dict):
            new_val = new_obj.get(field)
        else:
            new_val = getattr(new_obj, field, None) if new_obj is not None else None
        if old_val != new_val:
            old_data[field] = _serialize_value(old_val)
            new_data[field] = _serialize_value(new_val)
    return old_data, new_data


def log_audit(db, entity_type, entity_id, action, actor_user_id, old=None, new=None):
    try:
        old_payload = _serialize_payload(old or {})
        new_payload = _serialize_payload(new or {})
        diff = {
            "old": old_payload or {},
            "new": new_payload or {},
            "changed": _build_changed(old_payload, new_payload),
        }
        payload = json.dumps(diff, ensure_ascii=False)
        created_at = datetime.now(timezone.utc).isoformat()
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            created_at=created_at,
            diff_json=payload,
        )
        db.add(entry)
        return entry
    except Exception as exc:
        logger.warning(
            "audit_log_failed",
            extra={"entity_type": entity_type, "entity_id": entity_id, "action": action, "error": str(exc)},
        )
        return None
