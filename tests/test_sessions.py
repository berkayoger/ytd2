import os
import sys
from http.cookies import SimpleCookie

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import create_app, db
from backend.db.models import User, Role, UserSession


def test_login_creates_session_and_refresh(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    client = app.test_client()
    with app.app_context():
        user_role = Role.query.filter_by(name="user").first()
        user = User(username="testuser", api_key="apikey", role_id=user_role.id)
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "pass"},
    )
    assert response.status_code == 200
    cookies = SimpleCookie()
    cookies.load(response.headers.get("Set-Cookie"))
    refresh = cookies.get("refreshToken")
    assert refresh is not None
    with app.app_context():
        session_count = UserSession.query.count()
        assert session_count == 1

    # Use refresh token to obtain new tokens
    client.set_cookie("localhost", "refreshToken", refresh.value)
    refresh_resp = client.post("/api/auth/refresh")
    assert refresh_resp.status_code == 200


def test_refresh_rotates_session_token(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    client = app.test_client()
    with app.app_context():
        role = Role.query.filter_by(name="user").first()
        user = User(username="rotator", api_key="rotkey", role_id=role.id)
        user.set_password("pass")
        db.session.add(user)
        db.session.commit()

    login_resp = client.post(
        "/api/auth/login",
        json={"username": "rotator", "password": "pass"},
    )
    assert login_resp.status_code == 200
    cookies = SimpleCookie()
    cookies.load(login_resp.headers.get("Set-Cookie"))
    old_refresh = cookies.get("refreshToken").value

    with app.app_context():
        session_before = UserSession.query.first()
        old_hash = session_before.refresh_token

    client.set_cookie("localhost", "refreshToken", old_refresh)
    first_refresh = client.post("/api/auth/refresh")
    assert first_refresh.status_code == 200
    new_cookies = SimpleCookie()
    new_cookies.load(first_refresh.headers.get("Set-Cookie"))
    new_refresh = new_cookies.get("refreshToken").value
    assert new_refresh != old_refresh

    with app.app_context():
        session_after = UserSession.query.first()
        assert session_after.refresh_token != old_hash
        assert UserSession.query.count() == 1

    # old token should now be invalid
    client.set_cookie("localhost", "refreshToken", old_refresh)
    invalid = client.post("/api/auth/refresh")
    assert invalid.status_code == 401

    # new token should still work
    client.set_cookie("localhost", "refreshToken", new_refresh)
    valid = client.post("/api/auth/refresh")
    assert valid.status_code == 200
