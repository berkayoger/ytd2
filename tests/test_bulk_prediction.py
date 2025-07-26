import os
import sys
from types import SimpleNamespace

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import create_app, db
from backend.db.models import PredictionOpportunity
from backend.tasks import bulk_prediction


def test_generate_predictions_for_all_coins(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    with app.app_context():
        monkeypatch.setattr(
            bulk_prediction.cg,
            "get_coins_markets",
            lambda vs_currency="usd", per_page=5, page=1: [
                {"id": "bitcoin"},
                {"id": "ethereum"},
            ],
        )
        monkeypatch.setattr(
            bulk_prediction,
            "generate_ta_based_recommendation",
            lambda symbol: {"symbol": symbol.upper()},
        )
        monkeypatch.setattr(bulk_prediction, "fetch_current_price", lambda symbol: 100.0)

        created = bulk_prediction.generate_predictions_for_all_coins(limit=2)
        assert set(created) == {"BITCOIN", "ETHEREUM"}
        assert PredictionOpportunity.query.count() == 2
