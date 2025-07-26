from tests.factories import PromotionCodeFactory
import flask_jwt_extended
from backend.auth import middlewares
from backend import create_app, db
from flask.testing import FlaskClient
import os


def create_test_client(monkeypatch) -> FlaskClient:
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr(middlewares, "admin_required", lambda: (lambda f: f))
    import backend.api.admin.promotion_codes as pc
    monkeypatch.setattr(pc, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr(pc, "admin_required", lambda: (lambda f: f))
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.app_context():
        db.create_all()
    return app.test_client()


def test_promo_create(monkeypatch):
    client = create_test_client(monkeypatch)
    resp = client.post('/api/admin/promo/', json={
        "code": "NEW50",
        "description": "Yeni Kullanıcı",
        "promo_type": "discount",
        "discount_type": "%",
        "discount_amount": 50,
        "plans": "plan1",
        "usage_limit": 3,
        "active_days": 5,
        "validity_days": 10,
        "user_segment": "all",
        "custom_users": [],
    })
    assert resp.status_code in (200, 201)
    data = resp.get_json()
    assert data.get("ok") or data.get("id")


def test_promo_list(monkeypatch):
    client = create_test_client(monkeypatch)
    with client.application.app_context():
        PromotionCodeFactory()
    resp = client.get('/api/admin/promo/')
    data = resp.get_json()
    assert isinstance(data, list) or "promos" in data


def test_promo_delete(monkeypatch):
    client = create_test_client(monkeypatch)
    with client.application.app_context():
        promo = PromotionCodeFactory()
    resp = client.delete(f"/api/admin/promo/{promo.id}")
    assert resp.status_code in (200, 204)
