from backend.db.models import TechnicalIndicator, PredictionOpportunity
from sqlalchemy import desc
from backend.engine.strategic_decision_engine import advanced_decision_logic
from backend.utils.price_fetcher import fetch_current_price
from backend.db import db
from datetime import datetime, timedelta


def generate_ta_based_recommendation(symbol="bitcoin"):
    """Create a recommendation using the advanced decision engine."""
    indicator = (
        TechnicalIndicator.query.filter_by(symbol=symbol.upper())
        .order_by(desc(TechnicalIndicator.created_at))
        .first()
    )
    if not indicator:
        return None

    indicators = {
        "rsi": indicator.rsi,
        "macd": indicator.macd,
        "macd_signal": indicator.signal,
        "price": None,  # Can be filled with live price data
        "sma_10": None,
        "prev_predictions_success_rate": 0.75,
    }

    decision = advanced_decision_logic(indicators)
    if decision["signal"] == "avoid":
        return None

    return {
        "symbol": symbol.upper(),
        "rsi": indicator.rsi,
        "macd": indicator.macd,
        "signal": indicator.signal,
        "insight": decision,
        "created_at": indicator.created_at.isoformat(),
    }


def create_prediction_from_decision(symbol: str, indicators: dict) -> dict | None:
    """Verilen teknik göstergelere göre karar alır ve tahmin oluşturur."""
    decision = advanced_decision_logic(indicators)
    if decision["signal"] != "buy":
        return None

    price = fetch_current_price(symbol)
    if not price:
        return None

    prediction = PredictionOpportunity(
        symbol=symbol.upper(),
        current_price=price,
        target_price=round(price * 1.05, 2),
        expected_gain_pct=decision.get("expected_gain_pct", 5.0),
        expected_gain_days=decision.get("expected_gain_days"),
        description=decision.get("description"),
        confidence_score=int(decision["confidence"] * 100),
        trend_type="short_term",
        source_model="StrategicDecisionEngine",
        is_active=True,
        is_public=True,
        forecast_horizon="1d",
        created_at=datetime.utcnow(),
    )
    db.session.add(prediction)
    db.session.commit()
    return prediction.to_dict()
