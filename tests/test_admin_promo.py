import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import PromoCode, PromoCodeUsage, SubscriptionPlan, Role, User


def setup_admin(app):
    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        admin = User(username="adminuser", api_key="adminkey", role_id=role.id)
        admin.set_password("pass")
        # flag expected by admin_required
        admin.is_admin = True
        db.session.add(admin)
        db.session.commit()
    return admin


def create_promo(app):
    with app.app_context():
        promo = PromoCode(
            code="TEST",
            plan=SubscriptionPlan.BASIC,
            duration_days=10,
            max_uses=1,
            expires_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add(promo)
        db.session.commit()
    return promo


def test_update_expiration_success(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    client = app.test_client()
    setup_admin(app)
    promo = create_promo(app)

    new_date = datetime.utcnow() + timedelta(days=30)
    resp = client.patch(
        f"/api/admin/promo-codes/{promo.id}/expiration",
        json={"expires_at": new_date.isoformat()},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["expires_at"].startswith(new_date.date().isoformat())


def test_update_expiration_past_date(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    client = app.test_client()
    setup_admin(app)
    promo = create_promo(app)

    past_date = datetime.utcnow() - timedelta(days=1)
    resp = client.patch(
        f"/api/admin/promo-codes/{promo.id}/expiration",
        json={"expires_at": past_date.isoformat()},
    )
    assert resp.status_code == 400


def test_promo_usage_stats(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_ENGINE_OPTIONS", {}, raising=False)
    import types, sys
    sys.modules.setdefault("backend.core.routes", types.ModuleType("routes"))
    sys.modules.setdefault("pandas_ta", types.ModuleType("pandas_ta"))
    services_stub = types.ModuleType("services")
    services_stub.YTDCryptoSystem = object
    sys.modules["backend.core.services"] = services_stub
    import flask_jwt_extended
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr(flask_jwt_extended, "fresh_jwt_required", lambda *a, **k: (lambda f: f), raising=False)
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    client = app.test_client()
    setup_admin(app)

    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        user1 = User(username="u1", api_key="k1", role_id=role.id)
        user1.set_password("p")
        user2 = User(username="u2", api_key="k2", role_id=role.id)
        user2.set_password("p")
        promo1 = PromoCode(code="CODE1", plan=SubscriptionPlan.BASIC, duration_days=1, max_uses=5)
        promo2 = PromoCode(code="CODE2", plan=SubscriptionPlan.BASIC, duration_days=1, max_uses=5)
        db.session.add_all([user1, user2, promo1, promo2])
        db.session.commit()
        usage1 = PromoCodeUsage(promo_code_id=promo1.id, user_id=user1.id)
        usage2 = PromoCodeUsage(promo_code_id=promo1.id, user_id=user2.id)
        usage3 = PromoCodeUsage(promo_code_id=promo2.id, user_id=user1.id)
        db.session.add_all([usage1, usage2, usage3])
        db.session.commit()
        promo2.is_active = False
        db.session.commit()

    resp = client.get("/api/admin/promo-codes/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    items = data["items"]
    assert data["total"] == 2
    assert any(d["code"] == "CODE1" and d["count"] == 2 for d in items)
    assert any(d["code"] == "CODE2" and d["count"] == 1 for d in items)

    resp = client.get("/api/admin/promo-codes/stats?per_page=1&page=2")
    assert resp.status_code == 200
    data = resp.get_json()
    items = data["items"]
    assert len(items) == 1
    assert items[0]["code"] == "CODE2"

    resp = client.get("/api/admin/promo-codes/stats?include_inactive=false")
    assert resp.status_code == 200
    data = resp.get_json()
    items = data["items"]
    assert any(d["code"] == "CODE1" and d["count"] == 2 for d in items)
    assert not any(d["code"] == "CODE2" for d in items)


def test_promo_code_usage_details(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_ENGINE_OPTIONS", {}, raising=False)

    import types, sys
    sys.modules.setdefault("backend.core.routes", types.ModuleType("routes"))
    sys.modules.setdefault("pandas_ta", types.ModuleType("pandas_ta"))
    services_stub = types.ModuleType("services")
    services_stub.YTDCryptoSystem = object
    sys.modules["backend.core.services"] = services_stub

    import flask_jwt_extended
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr(flask_jwt_extended, "fresh_jwt_required", lambda *a, **k: (lambda f: f), raising=False)
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))

    app = create_app()
    client = app.test_client()
    setup_admin(app)

    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        user1 = User(username="u1", api_key="k1", role_id=role.id)
        user1.set_password("p")
        user2 = User(username="u2", api_key="k2", role_id=role.id)
        user2.set_password("p")
        promo = PromoCode(code="CODEX", plan=SubscriptionPlan.BASIC, duration_days=1, max_uses=5)
        db.session.add_all([user1, user2, promo])
        db.session.commit()
        usage1 = PromoCodeUsage(promo_code_id=promo.id, user_id=user1.id)
        usage2 = PromoCodeUsage(promo_code_id=promo.id, user_id=user2.id)
        db.session.add_all([usage1, usage2])
        db.session.commit()

    resp = client.get("/api/admin/promo-codes/stats/CODEX/usages")
    assert resp.status_code == 200
    data = resp.get_json()
    assert any(item["username"] == "u1" for item in data)
    assert any(item["username"] == "u2" for item in data)


def test_get_user_promos(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    client = app.test_client()
    setup_admin(app)

    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        user = User(username="userx", api_key="keyx", role_id=role.id)
        user.set_password("p")
        promo1 = PromoCode(code="UU1", plan=SubscriptionPlan.BASIC, duration_days=1, max_uses=1, assigned_user_id=1)
        db.session.add_all([user, promo1])
        db.session.commit()
        promo1.assigned_user_id = user.id
        db.session.commit()

    resp = client.get(f"/api/admin/promo-codes/user/{user.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert any(p["code"] == "UU1" for p in data)
