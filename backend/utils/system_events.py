import json
import logging
from backend.db import db
from backend.db.models import SystemEvent


logger = logging.getLogger(__name__)


def log_event(event_type: str, level: str, message: str, meta=None, user_id=None):
    """Create a SystemEvent entry and trigger alerts for high severity."""
    try:
        evt = SystemEvent(
            event_type=event_type,
            level=level,
            message=message,
            meta=json.dumps(meta or {}),
            user_id=user_id,
        )
        db.session.add(evt)
        db.session.commit()
    except Exception:  # pragma: no cover - log failures should not crash
        logger.exception("Failed to log system event")
        db.session.rollback()
        return

    if level.upper() in ("ERROR", "CRITICAL"):
        try:
            from backend.tasks.celery_tasks import send_security_alert_task

            send_security_alert_task.delay(event_type, message, severity=level.upper())
        except Exception:
            logger.exception("Failed to dispatch alert for system event")
