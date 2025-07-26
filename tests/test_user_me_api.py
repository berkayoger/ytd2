import os
import sys
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import User, Role, SubscriptionPlan


def setup_app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(
        "backend.Config.SQLALCHEMY_ENGINE_OPTIONS",
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        raising=False,
    )
    return create_app()


def create_user(app):
    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        user = User(username="profileuser", api_key="apikey", role_id=role.id, subscription_level=SubscriptionPlan.BASIC)
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()
    return user


def test_get_user_profile(monkeypatch):
    app = setup_app(monkeypatch)
    client = app.test_client()
    user = create_user(app)
    resp = client.get("/api/user/me", headers={"X-API-KEY": user.api_key})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["username"] == "profileuser"
    assert "limits" in data
