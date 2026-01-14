import json
from datetime import datetime, timezone

from ..db import AuditLog


def _serialize_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


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
    diff = {"old": old or {}, "new": new or {}}
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
