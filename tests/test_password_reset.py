import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import create_app, db
from backend.utils.token_helper import generate_reset_token, verify_reset_token


def test_generate_and_verify_token(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    with app.app_context():
        token = generate_reset_token("user@example.com")
        email = verify_reset_token(token)
        assert email == "user@example.com"
