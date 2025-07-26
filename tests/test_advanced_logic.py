import os
import sys
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.engine.rules import advanced_decision_logic, make_reliable_prediction


def test_buy_signal():
    inds = {
        "rsi": 25,
        "macd": 1.2,
        "macd_signal": 0.5,
        "price": 10,
        "sma_10": 9,
        "prev_predictions_success_rate": 0.8,
    }
    result = advanced_decision_logic(inds)
    assert result["signal"] == "buy"
    assert result["confidence"] >= 0.6


def test_avoid_signal():
    inds = {
        "rsi": 75,
        "macd": 0.5,
        "macd_signal": 1.0,
        "price": 10,
        "sma_10": 11,
        "prev_predictions_success_rate": 0.5,
    }
    result = advanced_decision_logic(inds)
    assert result["signal"] == "avoid"


def test_hold_signal_and_build_prediction():
    df = pd.DataFrame([{"price": 10, "symbol": "BTC"}])
    inds = {
        "rsi": 50,
        "macd": 0.5,
        "macd_signal": 0.5,
        "price": 10,
        "sma_10": 10,
        "prev_predictions_success_rate": 0.55,
    }
    pred = make_reliable_prediction(df, inds)
    assert pred is None
