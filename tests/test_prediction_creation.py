import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import PredictionOpportunity
from backend.tasks.strategic_recommender import create_prediction_from_decision


def test_create_prediction_from_decision(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    with app.app_context():
        monkeypatch.setattr(
            "backend.tasks.strategic_recommender.fetch_current_price", lambda symbol: 100.0
        )
        indicators = {
            "rsi": 25,
            "macd": 1.2,
            "macd_signal": 0.8,
            "price": 100,
            "sma_10": 98,
            "prev_predictions_success_rate": 0.75,
        }
        result = create_prediction_from_decision("bitcoin", indicators)
        assert result["symbol"] == "BITCOIN"
        assert result["expected_gain_days"] == "45-60"
        assert result["description"]
        assert PredictionOpportunity.query.count() == 1


def test_create_prediction_from_decision_no_buy(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    with app.app_context():
        monkeypatch.setattr(
            "backend.tasks.strategic_recommender.fetch_current_price", lambda symbol: 100.0
        )
        indicators = {
            "rsi": 80,
            "macd": 0.5,
            "macd_signal": 1.0,
            "price": 100,
            "sma_10": 110,
            "prev_predictions_success_rate": 0.5,
        }
        result = create_prediction_from_decision("bitcoin", indicators)
        assert result is None
        assert PredictionOpportunity.query.count() == 0

