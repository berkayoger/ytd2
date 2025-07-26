import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import create_app


def test_testing_config(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    assert app.config["TESTING"] is True


def test_price_cache_default(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    assert app.config["PRICE_CACHE_TTL"] == 0
