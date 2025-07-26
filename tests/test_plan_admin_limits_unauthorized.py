import json
import pytest
from backend import create_app, db

@pytest.fixture
def unauthorized_client(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("DISABLE_JWT_CHECKS", "1")
    monkeypatch.setattr("backend.auth.jwt_utils.require_admin", lambda f: f)
    monkeypatch.setattr("backend.auth.jwt_utils.require_csrf", lambda f: f)

    import sys
    sys.modules.pop("backend.api.plan_admin_limits", None)

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()


def test_create_plan_forbidden(unauthorized_client):
    try:
        response = unauthorized_client.post(
            "/api/plans/create",
            json={"name": "unauthorized", "price": 10, "features": {"predict": 5}},
        )
        assert response.status_code in (401, 403)
    except Exception as e:
        from flask_jwt_extended.exceptions import NoAuthorizationError
        assert isinstance(e, NoAuthorizationError)


def test_update_plan_limits_forbidden(unauthorized_client):
    # Create dummy plan as admin manually
    with unauthorized_client.application.app_context():
        from backend.models.plan import Plan
        p = Plan(name="temp", price=0, features=json.dumps({"predict": 1}))
        db.session.add(p)
        db.session.commit()
        plan_id = p.id

    try:
        response = unauthorized_client.post(
            f"/api/plans/{plan_id}/update-limits",
            json={"predict": 999}
        )
        assert response.status_code in (401, 403)
    except Exception as e:
        from flask_jwt_extended.exceptions import NoAuthorizationError
        assert isinstance(e, NoAuthorizationError)


def test_delete_plan_forbidden(unauthorized_client):
    try:
        response = unauthorized_client.delete("/api/plans/1")
        assert response.status_code in (401, 403)
    except Exception as e:
        from flask_jwt_extended.exceptions import NoAuthorizationError
        assert isinstance(e, NoAuthorizationError)
