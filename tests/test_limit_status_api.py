import json
from datetime import datetime

import flask_jwt_extended
import pytest

from backend import create_app, db
from flask import g
from backend.db.models import User, UsageLog, Role, UserRole
from backend.models.plan import Plan


@pytest.fixture
def test_app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.jwt_utils.require_csrf", lambda f: f)
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def test_user(test_app):
    with test_app.app_context():
        role = Role.query.filter_by(name="user").first()
        plan = Plan(name="basic", price=0.0, features=json.dumps({"predict_daily": 5}))
        db.session.add(plan)
        db.session.commit()
        user = User(username="limitstatus", role=UserRole.USER, plan_id=plan.id)
        user.set_password("pass")
        user.generate_api_key()
        db.session.add(user)
        db.session.commit()
        return user


def test_limit_status_endpoint(test_app, test_user):
    with test_app.app_context():
        db.session.add(
            UsageLog(user_id=test_user.id, action="predict_daily", timestamp=datetime.utcnow())
        )
        db.session.commit()
        token = test_user.generate_access_token()
    client = test_app.test_client()
    with test_app.app_context():
        g.user = db.session.merge(test_user)
        resp = client.get(
            "/api/limits/status",
            headers={
                "Authorization": f"Bearer {token}",
                "X-API-KEY": test_user.api_key,
                "X-CSRF-TOKEN": "test",
            },
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["limits"]["predict_daily"]["used"] == 1
    assert data["limits"]["predict_daily"]["remaining"] == 4
