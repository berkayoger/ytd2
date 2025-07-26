"""Utility endpoints and background tasks for prediction opportunities.

This module exposes a minimal CRUD API for managing prediction opportunities
as well as scheduled jobs that gather data from various sources.  The collected
data can later be used by the forecasting engine.  All endpoints in this
blueprint require admin privileges.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.db import db
from backend.db.models import PredictionOpportunity, TechnicalIndicator
from datetime import datetime, timedelta
from sqlalchemy import desc
from backend.utils.helpers import add_audit_log
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from pycoingecko import CoinGeckoAPI
import pandas_ta as ta
from scripts.crypto_ta import fetch_ohlc_data, calculate_indicators
import feedparser
import requests

from backend.utils.price_fetcher import fetch_current_price
from backend.tasks.bulk_prediction import generate_predictions_for_all_coins

predictions_bp = Blueprint("predictions", __name__, url_prefix="/api/admin/predictions")
logger = logging.getLogger(__name__)


@predictions_bp.route("/", methods=["GET"])
@jwt_required()
@admin_required()
def list_predictions():
    """Return all prediction opportunities in descending order of creation."""

    predictions = PredictionOpportunity.query.order_by(
        PredictionOpportunity.created_at.desc()
    ).all()
    return jsonify([p.to_dict() for p in predictions])


@predictions_bp.route("/public", methods=["GET"])
def public_predictions():
    """List public and active prediction opportunities."""
    predictions = PredictionOpportunity.query.filter_by(is_active=True, is_public=True).order_by(PredictionOpportunity.created_at.desc()).all()
    result = [
        {
            "symbol": p.symbol,
            "target_price": p.target_price,
            "expected_gain_pct": p.expected_gain_pct,
            "confidence_score": p.confidence_score,
            "trend_type": p.trend_type,
            "forecast_horizon": p.forecast_horizon,
            "created_at": p.created_at.isoformat(),
            "realized_gain_pct": p.realized_gain_pct,
            "fulfilled_at": p.fulfilled_at.isoformat() if p.fulfilled_at else None,
            "was_successful": p.was_successful
        } for p in predictions
    ]
    return jsonify(result), 200


@predictions_bp.route("/", methods=["POST"])
@jwt_required()
@admin_required()
def create_prediction():
    """Create a new prediction opportunity based on the posted JSON body."""

    data = request.get_json() or {}
    try:
        required_fields = ["symbol", "current_price", "target_price", "expected_gain_pct"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"'{field}' alanı zorunludur"}), 400

        created_at = datetime.utcnow()
        forecast_horizon = data.get("forecast_horizon")
        expires_at = None
        if forecast_horizon:
            try:
                num = int(forecast_horizon[:-1])
                unit = forecast_horizon[-1]
                if unit == 'd':
                    expires_at = created_at + timedelta(days=num)
                elif unit == 'h':
                    expires_at = created_at + timedelta(hours=num)
                elif unit == 'w':
                    expires_at = created_at + timedelta(weeks=num)
            except Exception:
                pass

        pred = PredictionOpportunity(
            symbol=data["symbol"].upper(),
            current_price=float(data["current_price"]),
            target_price=float(data["target_price"]),
            forecast_horizon=forecast_horizon,
            expected_gain_pct=float(data["expected_gain_pct"]),
            confidence_score=float(data.get("confidence_score", 0.0)),
            trend_type=data.get("trend_type", "short_term"),
            source_model=data.get("source_model", "AIModel"),
            is_active=bool(data.get("is_active", True)),
            is_public=bool(data.get("is_public", True)),
            created_at=created_at,
            expires_at=expires_at
        )
        db.session.add(pred)
        db.session.commit()
        add_audit_log(action_type="prediction_created", details={"symbol": pred.symbol})
        return jsonify(pred.to_dict()), 201
    except ValueError as ve:
        return jsonify({"error": f"Tip uyuşmazlığı: {str(ve)}"}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("Tahmin oluşturma hatası")
        return jsonify({"error": str(e)}), 400


@predictions_bp.route("/<int:prediction_id>", methods=["PATCH"])
@jwt_required()
@admin_required()
def update_prediction(prediction_id):
    """Partially update an existing prediction opportunity."""

    data = request.get_json() or {}
    pred = PredictionOpportunity.query.get_or_404(prediction_id)
    try:
        float_fields = ["current_price", "target_price", "expected_gain_pct", "confidence_score", "realized_gain_pct"]
        datetime_fields = ["fulfilled_at", "expires_at"]
        for field in [
            "symbol", "current_price", "target_price", "forecast_horizon",
            "expected_gain_pct", "confidence_score", "trend_type", "source_model",
            "is_active", "is_public", "realized_gain_pct", "fulfilled_at",
            "was_successful", "expires_at"
        ]:
            if field in data:
                value = data[field]
                if field in float_fields:
                    setattr(pred, field, float(value))
                elif field in datetime_fields:
                    setattr(pred, field, datetime.fromisoformat(value))
                elif field == "symbol":
                    setattr(pred, field, value.upper())
                else:
                    setattr(pred, field, value)
        db.session.commit()
        add_audit_log(action_type="prediction_updated", target_id=prediction_id, details=data)
        return jsonify(pred.to_dict()), 200
    except ValueError as ve:
        return jsonify({"error": f"Tip uyuşmazlığı: {str(ve)}"}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("Tahmin güncelleme hatası")
        return jsonify({"error": str(e)}), 400


@predictions_bp.route("/<int:prediction_id>", methods=["DELETE"])
@jwt_required()
@admin_required()
def delete_prediction(prediction_id):
    """Delete a prediction opportunity by its identifier."""

    pred = PredictionOpportunity.query.get_or_404(prediction_id)
    db.session.delete(pred)
    db.session.commit()
    add_audit_log(action_type="prediction_deleted", target_id=prediction_id, details={"symbol": pred.symbol})
    return jsonify({"message": "Silindi"}), 200


# Veri Toplama
cg = CoinGeckoAPI()


def fetch_price_data():
    """Fetch simple price data for Bitcoin and Ethereum from CoinGecko."""

    logger.info("[TASK] CoinGecko veri toplama başlatıldı")
    try:
        data = cg.get_price(ids='bitcoin,ethereum', vs_currencies='usd')
        logger.info(f"[DATA] Fiyat verisi: {data}")
    except Exception as e:
        logger.error(f"[ERROR] CoinGecko API hatası: {e}")


def fetch_technical_data():
    """Calculate a basic RSI indicator using pandas-ta."""

    logger.info("[TASK] Teknik analiz hesaplama başlatıldı")
    import pandas as pd
    df = pd.DataFrame({'close': [100, 102, 101, 105, 110]})
    rsi = ta.rsi(df['close'])
    logger.info(f"[DATA] RSI verisi: {rsi.dropna().to_list()}")


def fetch_news_rss():
    """Fetch a few recent headlines from CoinTelegraph RSS feed."""

    logger.info("[TASK] RSS haber toplama başlatıldı")
    feed = feedparser.parse('https://cointelegraph.com/rss')
    for entry in feed.entries[:3]:
        logger.info(f"[NEWS] {entry.title}")


def fetch_news_api():
    """Get crypto related news from NewsAPI using the demo key."""

    logger.info("[TASK] NewsAPI verisi çekiliyor")
    try:
        url = "https://newsapi.org/v2/everything?q=crypto&apiKey=demo"
        res = requests.get(url)
        if res.ok:
            articles = res.json().get("articles", [])
            for a in articles[:3]:
                logger.info(f"[API NEWS] {a['title']}")
    except Exception as e:
        logger.error(f"[ERROR] NewsAPI: {e}")


def fetch_social_signals():
    """Collect social sentiment data from LunarCrush."""

    logger.info("[TASK] LunarCrush sosyal verisi çekiliyor...")
    try:
        url = "https://api.lunarcrush.com/v2?data=assets&key=demo"
        res = requests.get(url)
        if res.ok:
            data = res.json().get("data", [])
            for asset in data[:3]:
                logger.info(
                    f"[SOCIAL] {asset['name']} - Galaxy Score: {asset.get('galaxy_score')}"
                )
        else:
            logger.warning(f"[SOCIAL] LunarCrush response: {res.status_code}")
    except Exception as e:
        logger.error(f"[SOCIAL] LunarCrush hata: {e}")


def fetch_event_calendar():
    """Retrieve upcoming events from CoinMarketCal."""

    logger.info("[TASK] CoinMarketCal etkinlikleri alınıyor...")
    try:
        headers = {
            "x-api-key": "YOUR_API_KEY",  # Gerçek anahtar gereklidir
        }
        url = "https://developers.coinmarketcal.com/v1/events"
        params = {
            "max": 3,
            "coins": "bitcoin",
            "page": 1,
        }
        res = requests.get(url, headers=headers, params=params)
        if res.ok:
            data = res.json().get("body", [])
            for ev in data:
                logger.info(f"[EVENT] {ev['title']} - {ev['date_event']}")
        else:
            logger.warning(f"[EVENT] CoinMarketCal response: {res.status_code}")
    except Exception as e:
        logger.error(f"[EVENT] CoinMarketCal hata: {e}")


def fetch_sentiment_news():
    """Collect news articles from Messari for sentiment analysis."""

    logger.info("[TASK] Messari haber verisi alınıyor...")
    try:
        url = "https://data.messari.io/api/v1/news"
        res = requests.get(url)
        if res.ok:
            articles = res.json().get("data", [])
            for article in articles[:3]:
                logger.info(
                    f"[NEWS] {article['title']} - {article['published_at']}"
                )
        else:
            logger.warning(f"[NEWS] Messari status: {res.status_code}")
    except Exception as e:
        logger.error(f"[NEWS] Messari API hatası: {e}")


def store_latest_ta(symbol="bitcoin"):
    """Fetch OHLC data and persist latest RSI/MACD values."""
    df = fetch_ohlc_data(coin_id=symbol)
    ta_df = calculate_indicators(df)
    latest = ta_df.iloc[-1]

    ti = TechnicalIndicator(
        symbol=symbol.upper(),
        rsi=float(latest["rsi"]),
        macd=float(latest["MACD_12_26_9"]),
        signal=float(latest["MACDs_12_26_9"]),
        created_at=datetime.utcnow(),
    )
    db.session.add(ti)
    db.session.commit()


def fetch_and_store_technical_indicators():
    logger.info("[TASK] Teknik analiz (RSI/MACD) hesaplama başlatıldı")
    try:
        store_latest_ta("bitcoin")
        logger.info("[TASK] Teknik analiz verisi kaydedildi")
    except Exception as e:
        logger.exception(f"[ERROR] Teknik analiz verisi alınamadı: {e}")


def generate_prediction_from_ta(symbol="bitcoin", threshold_gain: float = 3.0):
    """Create a short-term prediction using latest RSI and MACD values."""
    last_ta = (
        TechnicalIndicator.query
        .filter_by(symbol=symbol.upper())
        .order_by(desc(TechnicalIndicator.created_at))
        .first()
    )
    if not last_ta:
        return None

    rec = []
    if last_ta.rsi is not None and last_ta.rsi < 30:
        rec.append("RSI düşük, olası dönüş")
    if last_ta.macd is not None and last_ta.signal is not None:
        if last_ta.macd > last_ta.signal:
            rec.append("MACD kesişimi → Al")
        elif last_ta.macd < last_ta.signal:
            rec.append("MACD kesişimi → Sat")

    if not rec:
        return None

    current_price = fetch_current_price(symbol)
    if not current_price:
        logger.warning("[TA] Gerçek zamanlı fiyat alınamadı")
        return None
    prediction = PredictionOpportunity(
        symbol=symbol.upper(),
        current_price=current_price,
        target_price=round(current_price * (1 + threshold_gain / 100), 2),
        expected_gain_pct=threshold_gain,
        confidence_score=80,
        trend_type="short_term",
        source_model="TA-Strategy",
        is_active=True,
        is_public=True,
        forecast_horizon="1d",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    db.session.add(prediction)
    db.session.commit()
    return prediction.to_dict()

def evaluate_prediction_success():
    """Check active predictions and mark them as fulfilled when conditions met."""

    logger.info("[TASK] Tahmin başarı takibi başlatıldı")
    try:
        now = datetime.utcnow()
        active_preds = PredictionOpportunity.query.filter(
            PredictionOpportunity.is_active == True,
            PredictionOpportunity.fulfilled_at == None
        ).all()

        ids = list(set(p.symbol.lower() for p in active_preds))
        if not ids:
            return

        price_data = cg.get_price(ids=','.join(ids), vs_currencies='usd')

        for pred in active_preds:
            sym = pred.symbol.lower()
            if sym in price_data:
                current_price = price_data[sym]['usd']
                gain_pct = ((current_price - pred.current_price) / pred.current_price) * 100
                pred.realized_gain_pct = round(gain_pct, 2)
                if current_price >= pred.target_price:
                    pred.was_successful = True
                    pred.fulfilled_at = now
                    logger.info(f"[FULFILLED] {pred.symbol} hedefe ulaştı → %{gain_pct:.2f}")
                elif pred.expires_at and pred.expires_at < now:
                    pred.was_successful = False
                    pred.fulfilled_at = now
                    logger.info(f"[FAILED] {pred.symbol} süre doldu → %{gain_pct:.2f}")
        db.session.commit()
    except Exception as e:
        logger.error(f"[ERROR] Tahmin güncelleme: {e}")


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(fetch_price_data, 'interval', minutes=15, id="price_task")
scheduler.add_job(fetch_technical_data, 'interval', hours=1, id="tech_task")
scheduler.add_job(fetch_news_rss, 'interval', minutes=30, id="rss_task")
scheduler.add_job(fetch_news_api, 'interval', hours=2, id="news_task")
scheduler.add_job(fetch_social_signals, 'interval', hours=3, id="social_task")
scheduler.add_job(fetch_event_calendar, 'interval', hours=6, id="event_task")
scheduler.add_job(fetch_sentiment_news, 'interval', hours=4, id="sentiment_task")
scheduler.add_job(evaluate_prediction_success, 'interval', minutes=20, id="evaluate_predictions")
scheduler.add_job(fetch_and_store_technical_indicators, 'interval', minutes=30, id="technical_analysis")
scheduler.add_job(lambda: generate_prediction_from_ta("bitcoin"), 'interval', hours=2, id="ta_predictions")
scheduler.add_job(lambda: generate_predictions_for_all_coins(limit=10), 'interval', hours=6, id="bulk_ta_predictions")
scheduler.start()
