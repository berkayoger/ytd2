import pandas as pd
import pandas_ta as ta
import requests


# CoinGecko API üzerinden geçmiş fiyat verisi çekme
# Proxy restrictions may block network access, so fall back to sample data

def fetch_ohlc_data(coin_id="bitcoin", vs_currency="usd", days=7):
    """Fetch hourly OHLC data from CoinGecko or return sample data."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": vs_currency, "days": days, "interval": "hourly"}

    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        prices = data.get("prices", [])
    except Exception:
        # Offline fallback: generate simple increasing price series
        prices = []
        timestamp = pd.Timestamp.utcnow().floor("h") - pd.Timedelta(hours=days * 24)
        price = 100.0
        for _ in range(days * 24):
            prices.append([int(timestamp.timestamp() * 1000), price])
            timestamp += pd.Timedelta(hours=1)
            price += 1
        print("Unable to fetch data from CoinGecko, using sample dataset instead")

    df = pd.DataFrame(prices, columns=["timestamp", "price"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


def calculate_indicators(df):
    """Calculate RSI and MACD indicators."""
    df["rsi"] = ta.rsi(df["price"], length=14)
    macd = ta.macd(df["price"])
    df = df.join(macd)
    return df[["price", "rsi", "MACD_12_26_9", "MACDs_12_26_9", "MACDh_12_26_9"]]


if __name__ == "__main__":
    ohlc_data = fetch_ohlc_data("bitcoin", days=7)
    ta_result = calculate_indicators(ohlc_data)
    print(ta_result.tail())
