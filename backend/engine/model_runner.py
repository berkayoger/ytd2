def run_simple_rule_model(df):
    latest = df.iloc[-1]
    if latest["momentum"] > 0 and latest["price"] > latest["sma_10"]:
        return {"signal": "buy", "confidence": 0.85}
    return {"signal": "hold", "confidence": 0.4}
