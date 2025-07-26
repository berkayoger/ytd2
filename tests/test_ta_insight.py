import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import TechnicalIndicator
from backend.tasks.strategic_recommender import generate_ta_based_recommendation


def test_generate_ta_based_recommendation(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    with app.app_context():
        ti = TechnicalIndicator(symbol="BTC", rsi=20.0, macd=1.5, signal=1.0)
        db.session.add(ti)
        db.session.commit()
        data = generate_ta_based_recommendation("BTC")
        assert data["symbol"] == "BTC"
        assert data["insight"]["signal"] == "buy"
        assert data["insight"]["confidence"] > 0.5
