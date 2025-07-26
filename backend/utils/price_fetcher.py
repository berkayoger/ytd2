"""Utility function to fetch real-time crypto prices from CoinGecko."""

from __future__ import annotations

import requests
from loguru import logger


def fetch_current_price(symbol: str = "bitcoin", currency: str = "usd") -> float | None:
    """Return the current price of ``symbol`` in the given ``currency``.

    On any error or network issue ``None`` is returned instead of raising
    an exception.
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": symbol, "vs_currencies": currency}
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        return res.json().get(symbol, {}).get(currency)
    except Exception as exc:  # pragma: no cover - network calls
        logger.warning(f"Could not fetch price for {symbol}: {exc}")
        return None
