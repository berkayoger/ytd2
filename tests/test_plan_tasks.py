import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import User, Role, UserRole
from backend.models.plan import Plan


def setup_app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    return create_app()


def test_auto_downgrade_expired_plan(monkeypatch):
    app = setup_app(monkeypatch)
    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        free = Plan(name="Free", price=0.0)
        pro = Plan(name="Pro", price=10.0)
        db.session.add_all([free, pro])
        db.session.commit()
        user = User(
            username="planuser",
            api_key="plankey",
            role_id=role.id,
            role=UserRole.USER,
            plan_id=pro.id,
            plan_expire_at=datetime.utcnow() - timedelta(days=1),
        )
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()

        from backend.tasks.plan_tasks import auto_downgrade_expired_plans

        auto_downgrade_expired_plans.run()
        db.session.expire_all()
        updated = User.query.get(user.id)
        assert updated.plan_id == free.id
        assert updated.plan_expire_at is None


def test_auto_expire_boost(monkeypatch):
    app = setup_app(monkeypatch)
    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        user = User(
            username="boostuser",
            api_key="boostkey",
            role_id=role.id,
            role=UserRole.USER,
            boost_features="{\"t\":1}",
            boost_expire_at=datetime.utcnow() - timedelta(days=1),
        )
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()

        from backend.tasks.plan_tasks import auto_expire_boosts

        auto_expire_boosts.run()
        db.session.expire_all()
        updated = User.query.get(user.id)
        assert updated.boost_features is None
        assert updated.boost_expire_at is None

def test_activate_pending_plan(monkeypatch):
    app = setup_app(monkeypatch)
    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        base = Plan(name="Base", price=0.0)
        nextp = Plan(name="Next", price=5.0)
        db.session.add_all([base, nextp])
        db.session.commit()
        user = User(
            username="pendinguser",
            api_key="pendkey",
            role_id=role.id,
            role=UserRole.USER,
            plan_id=base.id,
        )
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()
        from backend.models.pending_plan import PendingPlan
        start_at = datetime.utcnow() - timedelta(minutes=1)
        expire_at = datetime.utcnow() + timedelta(days=1)
        pp = PendingPlan(user_id=user.id, plan_id=nextp.id, start_at=start_at, expire_at=expire_at)
        db.session.add(pp)
        db.session.commit()
        from backend.tasks.plan_tasks import activate_pending_plans
        activate_pending_plans.run()
        db.session.expire_all()
        updated = User.query.get(user.id)
        assert updated.plan_id == nextp.id
        assert updated.plan_expire_at == expire_at
        assert PendingPlan.query.count() == 0
