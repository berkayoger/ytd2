def build_prediction(df, model_output):
    if model_output["signal"] == "buy":
        current = df.iloc[-1]["price"]
        target = round(current * 1.05, 2)
        return {
            "symbol": df.iloc[-1]["symbol"],
            "current_price": current,
            "target_price": target,
            "confidence": model_output["confidence"],
            "trend_type": "short_term"
        }
    return None
