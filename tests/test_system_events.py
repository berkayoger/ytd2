import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import SystemEvent
from backend.utils.system_events import log_event


def setup_app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    return app


def test_log_and_list_events(monkeypatch):
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = setup_app(monkeypatch)
    client = app.test_client()

    with app.app_context():
        log_event("test", "INFO", "hello", {"a": 1})

    resp = client.get("/api/admin/events")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data and data[0]["message"] == "hello"


def test_retention_cleanup(monkeypatch):
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = setup_app(monkeypatch)
    client = app.test_client()

    with app.app_context():
        old_evt = SystemEvent(
            event_type="old",
            level="INFO",
            message="old",
            created_at=datetime.utcnow() - timedelta(days=10),
        )
        db.session.add(old_evt)
        db.session.commit()

    resp = client.post("/api/admin/events/retention-cleanup", json={"days": 5})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["deleted"] == 1


def test_system_status(monkeypatch):
    monkeypatch.setattr("flask_jwt_extended.jwt_required", lambda *a, **k: (lambda f: f))
    monkeypatch.setattr("backend.auth.middlewares.admin_required", lambda: (lambda f: f))
    app = setup_app(monkeypatch)
    client = app.test_client()

    resp = client.get("/api/admin/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "database" in data
