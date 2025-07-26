from flask import json
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import PredictionOpportunity
import flask_jwt_extended
import types
from sqlalchemy.pool import StaticPool


def test_create_and_list_predictions(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(
        "backend.Config.SQLALCHEMY_ENGINE_OPTIONS",
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        raising=False,
    )
    import types, sys
    sys.modules.setdefault("backend.core.routes", types.ModuleType("routes"))
    services_stub = types.ModuleType("services")
    services_stub.YTDCryptoSystem = object
    sys.modules["backend.core.services"] = services_stub
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr(flask_jwt_extended, "fresh_jwt_required", lambda *a, **k: (lambda f: f), raising=False)
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    monkeypatch.setattr("backend.auth.jwt_utils.require_csrf", lambda f: f)
    app = create_app()
    client = app.test_client()

    resp = client.post(
        "/api/admin/predictions/",
        data=json.dumps({
            "symbol": "BTC",
            "current_price": 30000,
            "target_price": 35000,
            "expected_gain_pct": 10
        }),
        content_type="application/json"
    )
    assert resp.status_code == 201

    resp = client.get("/api/admin/predictions/")
    data = resp.get_json()
    assert resp.status_code == 200
    assert any(p["symbol"] == "BTC" for p in data)


def test_update_and_delete_prediction(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(
        "backend.Config.SQLALCHEMY_ENGINE_OPTIONS",
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        raising=False,
    )
    import types, sys
    sys.modules.setdefault("backend.core.routes", types.ModuleType("routes"))
    services_stub = types.ModuleType("services")
    services_stub.YTDCryptoSystem = object
    sys.modules["backend.core.services"] = services_stub
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr(flask_jwt_extended, "fresh_jwt_required", lambda *a, **k: (lambda f: f), raising=False)
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    monkeypatch.setattr("backend.auth.jwt_utils.require_csrf", lambda f: f)
    app = create_app()
    client = app.test_client()

    with app.app_context():
        pred = PredictionOpportunity(
            symbol="ETH",
            current_price=2000,
            target_price=2200,
            expected_gain_pct=5
        )
        db.session.add(pred)
        db.session.commit()
        pid = pred.id

    resp = client.patch(
        f"/api/admin/predictions/{pid}",
        data=json.dumps({"target_price": 2300}),
        content_type="application/json"
    )
    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated["target_price"] == 2300

    resp = client.delete(f"/api/admin/predictions/{pid}")
    assert resp.status_code == 200


def test_filter_predictions_by_source_model(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(
        "backend.Config.SQLALCHEMY_ENGINE_OPTIONS",
        {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}},
        raising=False,
    )
    import types, sys
    sys.modules.setdefault("backend.core.routes", types.ModuleType("routes"))
    services_stub = types.ModuleType("services")
    services_stub.YTDCryptoSystem = object
    sys.modules["backend.core.services"] = services_stub
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr(flask_jwt_extended, "fresh_jwt_required", lambda *a, **k: (lambda f: f), raising=False)
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    monkeypatch.setattr("backend.auth.jwt_utils.require_csrf", lambda f: f)
    app = create_app()
    client = app.test_client()

    with app.app_context():
        p1 = PredictionOpportunity(symbol="BTC", current_price=30000, target_price=35000, expected_gain_pct=10, source_model="TA-Strategy")
        p2 = PredictionOpportunity(symbol="ETH", current_price=2000, target_price=2500, expected_gain_pct=5, source_model="Other")
        db.session.add_all([p1, p2])
        db.session.commit()

    resp = client.get("/api/admin/predictions/?source_model=TA-Strategy")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["total"] == 1
    assert data["items"][0]["source_model"] == "TA-Strategy"
