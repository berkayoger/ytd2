import json
import pytest
from backend import create_app, db
from backend.models.plan import Plan
from backend.auth import jwt_utils

@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.auth.jwt_utils.require_admin", lambda f: f)
    monkeypatch.setattr("backend.auth.jwt_utils.require_csrf", lambda f: f)

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


def test_full_plan_crud_flow(admin_client):
    # CREATE
    payload = {
        "name": "gold",
        "price": 29.99,
        "features": {"predict": 200, "analytics": 50},
    }
    resp_create = admin_client.post("/api/plans/create", json=payload)
    assert resp_create.status_code == 201
    created = resp_create.get_json()
    assert created["name"] == "gold"
    assert created["features"]["predict"] == 200
    pid = created["id"]

    # UPDATE
    update_payload = {"predict": 500, "analytics": 100}
    resp_update = admin_client.post(f"/api/plans/{pid}/update-limits", json=update_payload)
    assert resp_update.status_code == 200
    updated = resp_update.get_json()
    assert updated["plan"]["features"]["predict"] == 500

    # GET ALL
    resp_all = admin_client.get("/api/plans/all")
    assert resp_all.status_code == 200
    plans = resp_all.get_json()
    assert any(p["name"] == "gold" for p in plans)

    # DELETE
    resp_delete = admin_client.delete(f"/api/plans/{pid}")
    assert resp_delete.status_code == 200
    deleted = resp_delete.get_json()
    assert deleted["success"] is True

    # CONFIRM DELETE
    resp_check = admin_client.get("/api/plans/all")
    plans_after = resp_check.get_json()
    assert not any(p["id"] == pid for p in plans_after)


def test_create_plan_missing_name(admin_client):
    resp = admin_client.post("/api/plans/create", json={"price": 1})
    assert resp.status_code == 400


def test_create_plan_invalid_limit_value(admin_client):
    payload = {
        "name": "test",
        "features": {"predict": -5}  # invalid value
    }
    resp = admin_client.post("/api/plans/create", json=payload)
    assert resp.status_code in (400, 500)


def test_update_plan_limits_invalid_payload(admin_client):
    # Create a plan first
    resp_create = admin_client.post("/api/plans/create", json={"name": "x", "features": {"a": 1}})
    pid = resp_create.get_json()["id"]
    # Try updating with string
    resp = admin_client.post(f"/api/plans/{pid}/update-limits", json={"a": "invalid"})
    assert resp.status_code == 400


def test_delete_nonexistent_plan(admin_client):
    resp = admin_client.delete("/api/plans/999999")
    assert resp.status_code == 404
