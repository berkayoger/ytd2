def advanced_decision_logic(indicators: dict) -> dict:
    score = 0
    if indicators.get("rsi", 50) < 30:
        score += 2
    elif indicators.get("rsi", 50) > 70:
        score -= 2

    if indicators.get("macd", 0) > indicators.get("macd_signal", 0):
        score += 2
    else:
        score -= 1

    if indicators.get("price") is not None and indicators.get("sma_10") is not None:
        if indicators["price"] > indicators["sma_10"]:
            score += 1

    if indicators.get("prev_predictions_success_rate", 0) > 0.7:
        score += 1

    signal = "buy" if score >= 3 else "hold" if score >= 1 else "avoid"
    confidence = min(0.95, 0.6 + 0.1 * score)

    return {"signal": signal, "confidence": round(confidence, 2)}

from .decision_maker import build_prediction


def make_reliable_prediction(df, indicators):
    model_result = advanced_decision_logic(indicators)
    return build_prediction(df, model_result)
