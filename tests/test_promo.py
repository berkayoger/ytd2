import flask_jwt_extended
from backend.auth import middlewares
from backend import create_app, db
from flask.testing import FlaskClient
from tests.factories import PromotionCodeFactory
from backend.db.models import PromotionCode


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
        "code": "YENIKULLANICI50",
        "description": "YENİ KULLANICI İNDİRİMİ",
        "promo_type": "discount",
        "discount_type": "%",
        "discount": 50,
        "plans": "plan1",
        "usage_limit": 3,
        "active_days": 5,
        "validity_days": 10,
        "user_segment": "new_1m",
        "custom_users": [],
    })
    assert resp.status_code in (200, 201)
    data = resp.get_json()
    assert data.get("ok")


def test_promo_list(monkeypatch):
    client = create_test_client(monkeypatch)
    with client.application.app_context():
        PromotionCodeFactory()
    resp = client.get('/api/admin/promo/')
    data = resp.get_json()
    assert "promos" in data
    assert len(data["promos"]) > 0


def test_promo_delete(monkeypatch):
    client = create_test_client(monkeypatch)
    with client.application.app_context():
        promo = PromotionCodeFactory()
    resp = client.delete(f"/api/admin/promo/{promo.id}")
    assert resp.status_code in (200, 204)


def test_promo_segment_access(monkeypatch):
    client = create_test_client(monkeypatch)
    with client.application.app_context():
        promo = PromotionCodeFactory(user_segment="new_1m")
    resp = client.get('/api/admin/promo/')
    data = resp.get_json()
    assert any(p["userSegment"] == "new_1m" for p in data["promos"]) 


def test_promo_usage_limit(monkeypatch):
    client = create_test_client(monkeypatch)
    with client.application.app_context():
        promo = PromotionCodeFactory(usage_limit=2)
        promo.usage_count = 2
        db.session.commit()
        pid = promo.id
    with client.application.app_context():
        refreshed = PromotionCode.query.get(pid)
        assert refreshed.usage_count == 2
        assert refreshed.usage_limit == 2

