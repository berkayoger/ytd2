import json
import os
import sys
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import create_app, db
from backend.models.plan import Plan
from backend.db.models import User, Role, UserRole


def setup_app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(
        "backend.Config.SQLALCHEMY_ENGINE_OPTIONS",
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        raising=False,
    )
    return create_app()


def create_admin(app):
    with app.app_context():
        role = Role.query.filter_by(name="admin").first()
        admin = User(username="admin", api_key="adminkey", role_id=role.id, role=UserRole.ADMIN)
        admin.set_password("pass")
        db.session.add(admin)
        db.session.commit()


def test_plan_features_and_auth(monkeypatch):
    app = setup_app(monkeypatch)
    client = app.test_client()

    with app.app_context():
        p = Plan(name="Test", price=1.0, features=json.dumps({"a": 1}))
        db.session.add(p)
        db.session.commit()

    resp = client.get("/api/admin/plans")
    assert resp.status_code == 401

    create_admin(app)
    resp = client.get("/api/admin/plans", headers={"Authorization": "adminkey"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data[0]["features"]["a"] == 1
