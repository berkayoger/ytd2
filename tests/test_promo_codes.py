import os
import sys
from datetime import datetime, timedelta
from flask import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import PromoCode, SubscriptionPlan, User, Role


def setup_admin_user(app):
    with app.app_context():
        admin_role = Role.query.filter_by(name="admin").first()
        user = User(
            username="adminuser",
            email="admin@test.com",
            role_id=admin_role.id,
            api_key="adminkey123",
            subscription_level=SubscriptionPlan.PREMIUM
        )
        user.set_password("adminpass")
        db.session.add(user)
        db.session.commit()
        return user


def test_create_and_get_promo_code(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    client = app.test_client()
    setup_admin_user(app)

    headers = {"Authorization": "Bearer adminkey123"}

    resp = client.post(
        "/api/admin/promo-codes/",
        data=json.dumps({
            "code": "TRYFREE30",
            "plan": "BASIC",
            "duration_days": 30,
            "max_uses": 100
        }),
        content_type='application/json',
        headers=headers
    )
    assert resp.status_code == 201

    resp = client.get("/api/admin/promo-codes/", headers=headers)
    data = resp.get_json()
    assert resp.status_code == 200
    assert any(code["code"] == "TRYFREE30" for code in data)


def test_patch_and_delete_promo_code(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    client = app.test_client()
    setup_admin_user(app)

    headers = {"Authorization": "Bearer adminkey123"}

    with app.app_context():
        pc = PromoCode(
            code="TESTDELETE",
            plan=SubscriptionPlan.BASIC,
            duration_days=7,
            max_uses=1,
            current_uses=0,
            is_active=True
        )
        db.session.add(pc)
        db.session.commit()
        pid = pc.id

    resp = client.patch(
        f"/api/admin/promo-codes/{pid}",
        data=json.dumps({"max_uses": 5}),
        content_type='application/json',
        headers=headers
    )
    assert resp.status_code == 200

    resp = client.delete(f"/api/admin/promo-codes/{pid}", headers=headers)
    assert resp.status_code == 200


def test_user_email_handling(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    client = app.test_client()
    setup_admin_user(app)

    headers = {"Authorization": "Bearer adminkey123"}

    resp = client.post(
        "/api/admin/promo-codes/",
        data=json.dumps({
            "code": "EMAILTEST",
            "plan": "BASIC",
            "duration_days": 5,
            "max_uses": 1,
            "user_email": "target@test.com"
        }),
        content_type='application/json',
        headers=headers
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["user_email"] == "target@test.com"
    promo_id = data["id"]

    resp = client.patch(
        f"/api/admin/promo-codes/{promo_id}",
        data=json.dumps({"user_email": None}),
        content_type='application/json',
        headers=headers
    )
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated["user_email"] is None
