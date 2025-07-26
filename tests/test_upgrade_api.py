import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import create_app, db
from backend.db.models import User, Role, SubscriptionPlan


def setup_user(app, plan=SubscriptionPlan.BASIC):
    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        user = User(username="upgrader", api_key="upkey", role_id=role.id, subscription_level=plan)
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()
    return user


def test_upgrade_plan_success(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    client = app.test_client()
    user = setup_user(app)
    resp = client.patch(f"/api/users/{user.id}/upgrade_plan", json={"plan": "ADVANCED"}, headers={"X-API-KEY": user.api_key})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["subscription_level"] == "ADVANCED"
    with app.app_context():
        updated = User.query.get(user.id)
        assert updated.subscription_level == SubscriptionPlan.ADVANCED
