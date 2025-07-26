from datetime import datetime

from backend import db
from backend.db.models import UsageLog


def record_usage(user, action: str) -> UsageLog:
    """Persist a usage log entry for the given user action."""
    log = UsageLog(user_id=user.id, action=action, timestamp=datetime.utcnow())
    db.session.add(log)
    db.session.commit()
    return log
