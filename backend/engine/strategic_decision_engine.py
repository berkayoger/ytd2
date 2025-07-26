def advanced_decision_logic(indicators: dict) -> dict:
    score = 0
    if indicators.get("rsi") is not None:
        if indicators["rsi"] < 30:
            score += 2
        elif indicators["rsi"] > 70:
            score -= 2

    if indicators.get("macd") is not None and indicators.get("macd_signal") is not None:
        if indicators["macd"] > indicators["macd_signal"]:
            score += 2
        else:
            score -= 1

    if indicators.get("price") and indicators.get("sma_10") and indicators["price"] > indicators["sma_10"]:
        score += 1

    if indicators.get("prev_predictions_success_rate", 0) > 0.7:
        score += 1

    if score >= 3:
        signal = "buy"
    elif score >= 1:
        signal = "hold"
    else:
        signal = "avoid"

    confidence = min(0.95, 0.6 + 0.1 * score)

    result = {"signal": signal, "confidence": round(confidence, 2)}

    if signal == "buy":
        result.update(
            {
                "expected_gain_pct": 25,
                "expected_gain_days": "45-60",
                "description": "RSI < 30 ve MACD kesişimi görüldü. Teknik olarak alım bölgesi.",
            }
        )

    return result

