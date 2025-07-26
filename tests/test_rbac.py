import os
import sys
import pytest
from flask import request, jsonify

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import create_app, db
from backend.db.models import Role, Permission, User, UserRole


def fake_admin_required():
    def wrapper(fn):
        def decorated(*args, **kwargs):
            api_key = request.headers.get("X-API-KEY")
            user = User.query.filter_by(api_key=api_key).first()
            if not user or user.role != UserRole.ADMIN:
                return jsonify({"error": "Admin yetkisi gereklidir!"}), 403
            return fn(*args, **kwargs)
        return decorated
    return wrapper


def test_rbac_init_creates_roles_permissions(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    with app.app_context():
        role = Role.query.filter_by(name="admin").first()
        perm = Permission.query.filter_by(name="admin_access").first()
        assert role is not None
        assert perm is not None
        assert perm in role.permissions


def test_admin_permission_denied(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("ADMIN_ACCESS_KEY", "secret")
    monkeypatch.setattr("backend.auth.middlewares.admin_required", fake_admin_required)
    app = create_app()
    client = app.test_client()
    with app.app_context():
        user_role = Role.query.filter_by(name="user").first()
        user = User(username="tester", api_key="testkey", role_id=user_role.id)
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()

    resp = client.get(
        "/api/admin/users/",
        headers={"X-ADMIN-API-KEY": "secret", "X-API-KEY": "testkey"},
    )
    assert resp.status_code == 200


def test_admin_permission_granted(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("ADMIN_ACCESS_KEY", "secret")
    monkeypatch.setattr("backend.auth.middlewares.admin_required", fake_admin_required)
    app = create_app()
    client = app.test_client()
    with app.app_context():
        admin_role = Role.query.filter_by(name="admin").first()
        admin = User(username="admintest", api_key="adminkey", role_id=admin_role.id, role=UserRole.ADMIN)
        admin.set_password("pass")
        db.session.add(admin)
        db.session.commit()

    resp = client.get(
        "/api/admin/users/",
        headers={"X-ADMIN-API-KEY": "secret", "X-API-KEY": "adminkey"},
    )
    assert resp.status_code == 200
