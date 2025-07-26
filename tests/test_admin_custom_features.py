import json
import pytest

from backend import create_app, db
from backend.db.models import User, Role, UserRole


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr("backend.Config.SQLALCHEMY_ENGINE_OPTIONS", {}, raising=False)
    import flask_jwt_extended
    monkeypatch.setattr(flask_jwt_extended, "jwt_required", lambda *a, **k: (lambda f: f), raising=False)
    monkeypatch.setattr(flask_jwt_extended, "fresh_jwt_required", lambda *a, **k: (lambda f: f), raising=False)
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        role = Role.query.filter_by(name="admin").first()
        if not role:
            role = Role(name="admin")
            db.session.add(role)
            db.session.commit()
        admin = User(username="admin", api_key="adminkey", role=UserRole.ADMIN, role_id=role.id)
        admin.set_password("adminpass")
        db.session.add(admin)
        db.session.commit()
    return app.test_client()


@pytest.fixture
def admin_headers():
    return {"X-API-KEY": "adminkey"}


@pytest.fixture
def test_user(client):
    with client.application.app_context():
        role = Role.query.filter_by(name="user").first()
        if not role:
            role = Role(name="user")
            db.session.add(role)
            db.session.commit()
        user = User(username="tester", api_key="testkey", role=UserRole.USER, role_id=role.id)
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()
    return user


def test_admin_can_update_custom_features(client, admin_headers, test_user):
    payload = {
        "custom_features": json.dumps({
            "can_export_csv": True,
            "predict_daily": 99,
        })
    }

    res = client.post(
        f"/api/admin/users/{test_user.id}/custom-features",
        headers=admin_headers,
        json=payload,
    )

    assert res.status_code == 200
    data = res.get_json()
    assert data["message"] == "Özel özellikler güncellendi."

    from backend.db.models import User
    with client.application.app_context():
        updated = User.query.get(test_user.id)
        features = json.loads(updated.custom_features)
    assert features["can_export_csv"] is True
    assert features["predict_daily"] == 99


def test_update_custom_features_invalid_json(client, admin_headers, test_user):
    invalid_payload = {"custom_features": "{invalid: json,"}
    resp = client.post(
        f"/api/admin/users/{test_user.id}/custom-features",
        json=invalid_payload,
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert resp.get_json().get("error") == "Geçersiz JSON"


def test_update_custom_features_user_not_found(client, admin_headers):
    resp = client.post(
        "/api/admin/users/999/custom-features",
        json={"custom_features": "{}"},
        headers=admin_headers,
    )
    assert resp.status_code == 404
    assert resp.get_json().get("error") == "Kullanıcı bulunamadı"

