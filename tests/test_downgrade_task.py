import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import User, Role, SubscriptionPlan


def test_downgrade_expired_subscription(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    from backend.tasks.celery_tasks import check_and_downgrade_subscriptions

    app = create_app()

    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        if not role:
            role = Role(name="user")
            db.session.add(role)
            db.session.commit()

        expired_user = User(
            username="expired",
            api_key="expiredkey",
            role_id=role.id,
            subscription_level=SubscriptionPlan.PREMIUM,
            subscription_end=datetime.utcnow() - timedelta(days=1),
        )
        expired_user.set_password("pass")
        db.session.add(expired_user)
        db.session.commit()

        check_and_downgrade_subscriptions.run()

        updated = User.query.get(expired_user.id)
        assert updated.subscription_level == SubscriptionPlan.BASIC
        assert updated.subscription_end is None
