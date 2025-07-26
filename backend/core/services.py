# File: backend/core/services.py

import os
import json
import yaml
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests
import redis
from flask import current_app
from loguru import logger
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
import pandas_ta as ta

# İsteğe bağlı ağır kütüphaneler
try:
    from prophet import Prophet
except ImportError:
    Prophet = None

try:
    from transformers import pipeline as _pipeline
except ImportError:
    _pipeline = None

from backend.db import db
from backend.db.models import ABHData, DBHData, User, SubscriptionPlan
from backend.constants import BASIC_ALLOWED_COINS, BASIC_WEEKLY_VIEW_LIMIT
from backend.utils.helpers import bulk_insert_records
from backend.tasks import run_full_analysis  # Celery task


# Karar kurallarını yükle (YAML veya Flask config içinden)
RULES_CONFIG: Dict[str, Any] = {}
_config_path = current_app.config.get("DECISION_RULES_PATH")
if _config_path and os.path.exists(_config_path):
    with open(_config_path) as f:
        RULES_CONFIG = yaml.safe_load(f)
else:
    RULES_CONFIG = current_app.config.get("DECISION_RULES", {})


@dataclass
class AnalysisResult:
    coin: str
    timestamp: datetime

    # Teknik indikatörler
    rsi: float
    macd: float
    bb_upper: float
    bb_lower: float
    stochastic: float
    candlestick_pattern: str

    # Duygu analizi
    news_sentiment: float
    twitter_sentiment: float
    social_volume: int

    # On-chain veriler
    active_addresses: int
    exchange_inflow: float
    exchange_outflow: float

    # Tahmin
    forecast_next_day: Optional[float]
    forecast_explanation: str
    forecast_upper_bound: Optional[float]
    forecast_lower_bound: Optional[float]

    # Diğer
    volatility: float

    # Karar motoru çıktıları
    signal: str
    confidence: float
    risk_level: str
    suggested_stop_loss: float
    suggested_position_size: float


class HTTPClient:
    """
    Tek bir Session üzerinden retry ve timeout ayarlı HTTP istekleri.
    """

    _session: Optional[requests.Session] = None

    @classmethod
    def session(cls) -> requests.Session:
        if cls._session is None:
            s = requests.Session()
            adapter = HTTPAdapter(max_retries=3)
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            cls._session = s
        return cls._session

    @classmethod
    def get(cls, url: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", 10)
        return cls.session().get(url, timeout=timeout, **kwargs)


class DataCollector:
    """
    Fiyat, on-chain, sosyal medya ve haber verilerini toplayıp önbelleğe alır,
    ham verileri ABHData tablosuna yazar.
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = current_app.extensions.get("redis_client")
        self.chain_url: Optional[str] = current_app.config.get("ONCHAIN_API_URL")
        self.news_key: Optional[str] = current_app.config.get("NEWS_API_KEY")
        self.cache_ttl: int = int(current_app.config.get("PRICE_CACHE_TTL", 300))

    def collect_price_data(self, coin: str) -> Dict[str, Any]:
        cache_key = f"price:{coin}"
        if self.redis and self.cache_ttl > 0:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)

        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
            params = {"vs_currency": "usd", "days": 30}
            resp = HTTPClient.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            prices = [p[1] for p in data["prices"]]
            times = [
                datetime.fromtimestamp(p[0] / 1000).isoformat() for p in data["prices"]
            ]
            indicators = self._calc_indicators(prices)

            result: Dict[str, Any] = {
                "coin": coin,
                "current_price": prices[-1],
                "prices": prices,
                "times": times,
                **indicators,
            }

            # Ham veriyi kaydet
            entry = ABHData(
                source="coingecko",
                type="price",
                content=json.dumps(result),
                timestamp=datetime.utcnow().isoformat(),
                coin=coin,
                tags=json.dumps(["price", "technical"]),
            )
            bulk_insert_records([entry])

            # Redis önbelleğe yaz
            if self.redis and self.cache_ttl > 0:
                self.redis.set(cache_key, json.dumps(result), ex=self.cache_ttl)

            return result

        except RequestException as e:
            logger.error(f"Price fetch error ({coin}): {e}")
            raise

    def _calc_indicators(self, prices: List[float]) -> Dict[str, float]:
        series = pd.Series(prices)
        rsi = float(ta.rsi(series).iloc[-1]) if len(series) > 14 else 50.0
        macd = (
            float(ta.macd(series)["MACD_12_26_9"].iloc[-1]) if len(series) > 26 else 0.0
        )
        bb = ta.bbands(series)
        stochastic = (
            float(ta.stoch(series)["STOCHk_14_3_3"].iloc[-1])
            if len(series) > 14
            else 50.0
        )
        # Çok basit bir mum çubuğu formasyonu stub’u
        candlestick_pattern = "None"

        return {
            "rsi": rsi,
            "macd": macd,
            "bb_upper": float(bb["BBU_20_2.0"].iloc[-1]),
            "bb_lower": float(bb["BBL_20_2.0"].iloc[-1]),
            "stochastic": stochastic,
            "candlestick_pattern": candlestick_pattern,
        }

    def collect_onchain_data(self, coin: str) -> Dict[str, Any]:
        # TODO: Glassnode, Nansen vs. API çağrıları
        return {"active_addresses": 0, "exchange_inflow": 0.0, "exchange_outflow": 0.0}

    def collect_social_data(self, coin: str) -> Dict[str, Any]:
        # TODO: Twitter/Reddit entegrasyonu
        return {"twitter_sentiment": 0.0, "social_volume": 0}

    def collect_news_data(self, coin: str) -> List[Dict[str, Any]]:
        # TODO: Haber API entegrasyonu ve ABHData yazımı
        return []


class AIInterpreter:
    """
    Duygu analizi ve tahmin işlemleri.
    """

    def __init__(self):
        self.pipeline = _pipeline("sentiment-analysis") if _pipeline else None
        self.fallback = current_app.config.get("SENTIMENT_KEYWORDS", {})

    def analyze_sentiment(self, text: str) -> Tuple[str, float]:
        if self.pipeline:
            try:
                out = self.pipeline(text)[0]
                return out["label"].lower(), out["score"]
            except Exception as e:
                logger.warning(f"Sentiment pipeline error: {e}")
        # Basit kelime sayma fallback
        lower = text.lower()
        pos = sum(lower.count(w) for w in self.fallback.get("positive", []))
        neg = sum(lower.count(w) for w in self.fallback.get("negative", []))
        if pos > neg:
            return "positive", min(0.9, 0.5 + 0.1 * pos)
        if neg > pos:
            return "negative", min(0.9, 0.5 + 0.1 * neg)
        return "neutral", 0.5

    def forecast(
        self,
        prices: List[float],
        times: List[str],
        days: int = 1,
        coin_name: Optional[str] = None,
    ) -> Tuple[
        Optional[float | List[float]],
        str,
        Dict[str, Optional[float] | List[float]],
        List[str],
        float,
        str,
    ]:
        """Return Prophet based forecast for ``days`` days.

        The first three return values maintain backwards compatibility
        (prediction(s), method name and bounds).  Additional values
        provide the prediction dates, a confidence score calculated from
        the prediction band width and a short explanation string.
        """
        if Prophet and len(prices) >= 30:
            df = pd.DataFrame({"ds": pd.to_datetime(times), "y": prices})
            try:
                model = Prophet(yearly_seasonality=True, weekly_seasonality=True)
                model.fit(df)
                future = model.make_future_dataframe(
                    periods=days, include_history=False
                )
                forecast = model.predict(future)

                yhat = forecast["yhat"].astype(float).tolist()
                uppers = (
                    forecast.get("yhat_upper", forecast["yhat"]).astype(float).tolist()
                )
                lowers = (
                    forecast.get("yhat_lower", forecast["yhat"]).astype(float).tolist()
                )
                dates = forecast["ds"].dt.strftime("%Y-%m-%d").tolist()

                # Confidence based on prediction band width
                mean_y = float(np.mean(yhat)) if yhat else 0.0
                band_width = (
                    float(np.mean(np.array(uppers) - np.array(lowers))) if yhat else 0.0
                )
                confidence = 0.0
                if mean_y:
                    confidence = 1 - band_width / mean_y
                    confidence = max(0.0, min(confidence, 1.0))

                explanation = self._summarize_forecast(yhat, coin_name or "")

                if days == 1:
                    return (
                        yhat[0],
                        "prophet",
                        {"upper": uppers[0], "lower": lowers[0]},
                        [dates[0]],
                        confidence,
                        explanation,
                    )
                return (
                    yhat,
                    "prophet",
                    {"upper": uppers, "lower": lowers},
                    dates,
                    confidence,
                    explanation,
                )
            except Exception as e:  # pragma: no cover - logging
                logger.error(f"Prophet forecast error: {e}")
                return None, "error", {"upper": None, "lower": None}, [], 0.0, ""

        return None, "disabled", {"upper": None, "lower": None}, [], 0.0, ""

    def _summarize_forecast(self, preds: List[float], coin_name: str) -> str:
        if not preds:
            return ""
        trend = "artış" if preds[-1] >= preds[0] else "düşüş"
        return (
            f"Son {len(preds)} gündeki trend göz önüne alındığında "
            f"{coin_name} fiyatında {trend} bekleniyor."
        )


class DecisionEngine:
    """
    Profil bazlı al/sat/bekle kararları.
    """

    def __init__(self):
        self.rules = RULES_CONFIG

    def decide(self, analysis: Dict[str, Any], profile: str) -> Dict[str, Any]:
        rules = self.rules.get(profile, self.rules.get("moderate", {}))
        vol = analysis.get("volatility", 1.0)
        factor = 1.0 / (1 + vol)

        buy_score = 0.0
        sell_score = 0.0
        for cond in rules.get("buy", []):
            if self._match(cond, analysis):
                buy_score += cond.get("weight", 1) * factor
        for cond in rules.get("sell", []):
            if self._match(cond, analysis):
                sell_score += cond.get("weight", 1) * factor

        threshold = rules.get("threshold", 10)
        if buy_score > sell_score and buy_score > threshold:
            signal = "BUY"
            confidence = min(0.95, 0.5 + 0.01 * buy_score)
        elif sell_score > buy_score and sell_score > threshold:
            signal = "SELL"
            confidence = min(0.95, 0.5 + 0.01 * sell_score)
        else:
            signal = "HOLD"
            confidence = 0.5

        current_price = analysis.get("current_price", 0.0)
        stop_loss = current_price * (1 - rules.get("stop_loss_pct", 0.05))
        position_size = rules.get("position_size_pct", 0.1)

        return {
            "signal": signal,
            "confidence": confidence,
            "stop_loss": stop_loss,
            "position_size_pct": position_size,
        }

    def _match(self, cond: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
        metric = cond.get("metric")
        op = cond.get("operator")
        val = cond.get("value")
        if metric not in analysis:
            return False
        actual = analysis[metric]
        if op == ">":
            return actual > val
        if op == "<":
            return actual < val
        if op == "==":
            return actual == val
        return False


class YTDCryptoSystem:
    """
    Tüm pipeline’ı bir Celery görevi üzerinden başlatan üst seviye sınıf.
    """

    def __init__(self):
        self.collector = DataCollector()
        self.ai = AIInterpreter()
        self.engine = DecisionEngine()
        self.redis = current_app.extensions.get("redis_client")

    def analyze(
        self, coin: str, profile: str, user: Optional[User] = None
    ) -> Dict[str, Any]:
        # Asenkron görev tetikle
        task = run_full_analysis.delay(coin, profile, user.id if user else None)
        return {"status": "pending", "task_id": task.id}

    def save_to_dbh(self, analysis: AnalysisResult):
        with current_app.app_context():
            record = DBHData(
                coin=analysis.coin,
                timestamp=analysis.timestamp.isoformat(),
                # Teknik indikatörler
                rsi=analysis.rsi,
                macd=analysis.macd,
                bb_upper=analysis.bb_upper,
                bb_lower=analysis.bb_lower,
                # Duygu analizi
                news_sentiment=analysis.news_sentiment,
                twitter_sentiment=analysis.twitter_sentiment,
                social_volume=analysis.social_volume,
                # On-chain veriler
                active_addresses=analysis.active_addresses,
                exchange_inflow=analysis.exchange_inflow,
                exchange_outflow=analysis.exchange_outflow,
                # Tahmin
                forecast_next_day=analysis.forecast_next_day,
                forecast_upper_bound=analysis.forecast_upper_bound,
                forecast_lower_bound=analysis.forecast_lower_bound,
                forecast_explanation=analysis.forecast_explanation,
                volatility=analysis.volatility,
                # Karar motoru
                signal=analysis.signal,
                confidence=analysis.confidence,
                risk_level=analysis.risk_level,
                suggested_stop_loss=analysis.suggested_stop_loss,
                suggested_position_size=analysis.suggested_position_size,
            )
            db.session.add(record)
            db.session.commit()

    def backtest_rules(
        self, coin: str, profile: str, start: str, end: str
    ) -> Dict[str, Any]:
        # Geriye dönük test için DBHData’dan al
        records = DBHData.query.filter(
            DBHData.coin == coin, DBHData.timestamp >= start, DBHData.timestamp <= end
        ).all()

        wins = trades = 0
        for rec in records:
            # Burada örnek olarak sinyal yüzdesi RSI olarak kullanıldı
            analysis_stub = {
                "current_price": rec.rsi,
                **{
                    field: getattr(rec, field)
                    for field in (
                        "rsi",
                        "macd",
                        "bb_upper",
                        "bb_lower",
                        "stochastic_oscillator",
                    )
                    if hasattr(rec, field)
                },
            }
            out = self.engine.decide(analysis_stub, profile)
            trades += 1
            if out["signal"] in ("BUY", "SELL"):
                wins += 1

        return {
            "profit_pct": 0.0,
            "trades": trades,
            "win_rate": (wins / trades) if trades else 0.0,
        }
