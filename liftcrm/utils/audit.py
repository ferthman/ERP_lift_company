import json
import logging

from ..db import SessionLocal, AuditLog

logger = logging.getLogger(__name__)


def log_audit(entity_type, entity_id, action, actor_user, old=None, new=None, meta=None):
    payload = None
    if old is not None or new is not None:
        payload = {"old": old or {}, "new": new or {}}
    elif meta is not None:
        payload = {"meta": meta}
    try:
        diff_json = json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None
        with SessionLocal() as db:
            log_row = AuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_user_id=getattr(actor_user, "id", None),
                diff_json=diff_json,
            )
            db.add(log_row)
            db.commit()
    except Exception:
        logger.warning(
            "audit log write failed",
            exc_info=True,
            extra={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "actor_user_id": getattr(actor_user, "id", None),
            },
        )
