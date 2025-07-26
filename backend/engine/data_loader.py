import pandas as pd
from datetime import datetime, timedelta


def load_sample_price_data(symbol="BTC", hours=48):
    """Sahte fiyat verisi üretir (canlı API yerine)."""
    now = datetime.utcnow()
    timestamps = [now - timedelta(hours=i) for i in range(hours)][::-1]
    prices = [100 + i * 0.5 for i in range(hours)]  # basit artan fiyat
    df = pd.DataFrame({"timestamp": timestamps, "price": prices})
    df["symbol"] = symbol
    return df
