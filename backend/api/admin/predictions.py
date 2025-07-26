from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.auth.jwt_utils import require_csrf
from backend.db import db
from backend.db.models import PredictionOpportunity
from datetime import datetime, timedelta
from backend.utils.helpers import add_audit_log
import logging

# Admin paneli tahmin yönetimi için Blueprint tanımı
predictions_bp = Blueprint("predictions", __name__, url_prefix="/api/admin/predictions")
logger = logging.getLogger(__name__)


@predictions_bp.route("/", methods=["GET"])
@jwt_required()
@admin_required()
def list_predictions():
    """Tahmin fırsatlarını sayfalı ve filtreli olarak listeler."""
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        sort_by = request.args.get("sort_by", "created_at")
        order = request.args.get("order", "desc")
        symbol = request.args.get("symbol")
        is_successful = request.args.get("was_successful")
        source_model = request.args.get("source_model")

        query = PredictionOpportunity.query

        if symbol:
            query = query.filter(PredictionOpportunity.symbol.ilike(f"%{symbol}%"))
        if is_successful in ["true", "false"]:
            success_val = is_successful == "true"
            query = query.filter(PredictionOpportunity.was_successful == success_val)
        if source_model:
            query = query.filter(PredictionOpportunity.source_model == source_model)

        if order == "desc":
            query = query.order_by(getattr(PredictionOpportunity, sort_by).desc())
        else:
            query = query.order_by(getattr(PredictionOpportunity, sort_by).asc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Basit listeleme durumunda yalnızca tahmin dizisini döndür
        if not request.args:
            return jsonify([p.to_dict() for p in pagination.items])

        return jsonify({
            "total": pagination.total,
            "page": pagination.page,
            "per_page": pagination.per_page,
            "pages": pagination.pages,
            "items": [p.to_dict() for p in pagination.items]
        })
    except Exception as e:
        logger.error(f"[ERROR] Tahmin listeleme hatası: {e}")
        return jsonify({"error": str(e)}), 400


@predictions_bp.route("/public", methods=["GET"])
def public_predictions():
    """Kullanıcılara açık önerileri listeler."""
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        trend_type = request.args.get("trend_type")
        min_confidence = request.args.get("min_confidence", type=float)
        symbol = request.args.get("symbol")
        duration_range = request.args.get("duration_range")

        q = PredictionOpportunity.query.filter_by(is_active=True, is_public=True)

        if trend_type:
            q = q.filter(PredictionOpportunity.trend_type == trend_type)
        if min_confidence is not None:
            q = q.filter(PredictionOpportunity.confidence_score >= min_confidence)
        if symbol:
            q = q.filter(PredictionOpportunity.symbol.ilike(f"%{symbol}%"))
        if duration_range:
            try:
                min_days, max_days = duration_range.split("-")
                q = q.filter(PredictionOpportunity.expected_gain_days.ilike(f"{min_days}-%"))
            except Exception:
                pass

        total = q.count()
        predictions = (
            q.order_by(PredictionOpportunity.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        result = []
        for p in predictions:
            result.append(
                {
                    "symbol": p.symbol,
                    "signal": "buy",
                    "confidence": round((p.confidence_score or 0) / 100, 2),
                    "expected_gain_pct": p.expected_gain_pct,
                    "expected_gain_days": p.expected_gain_days,
                    "description": p.description,
                    "trend_type": p.trend_type,
                    "created_at": p.created_at.isoformat(),
                }
            )

        confidence_scores = [
            p.confidence_score for p in predictions if p.confidence_score is not None
        ]
        min_conf_range = [round(min(confidence_scores), 1), 100] if confidence_scores else [0, 100]

        return (
            jsonify(
                {
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "items": result,
                    "filters": {
                        "available_trend_types": sorted(
                            set(p.trend_type for p in predictions if p.trend_type)
                        ),
                        "min_confidence_range": min_conf_range,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        logger.error("Public prediction fetch error", exc_info=e)
        return jsonify({"error": "Beklenmeyen hata oluştu."}), 500


@predictions_bp.route("/", methods=["POST"])
@jwt_required()
@admin_required()
@require_csrf
def create_prediction():
    """Yeni bir tahmin fırsatı oluşturur."""
    data = request.get_json() or {}
    try:
        # Gerekli alanların varlığını kontrol et
        required_fields = ["symbol", "current_price", "target_price", "expected_gain_pct"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"'{field}' alanı zorunludur"}), 400

        symbol = data["symbol"].strip().upper()
        current_price = float(data["current_price"])
        target_price = float(data["target_price"])
        expected_gain = float(data["expected_gain_pct"])
        confidence = float(data.get("confidence_score", 0.0))

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

        if len(symbol) > 20:
            return jsonify({"error": "Symbol en fazla 20 karakter olabilir"}), 400
        if current_price < 0 or target_price < 0:
            return jsonify({"error": "Fiyatlar negatif olamaz"}), 400
        if not -100 <= expected_gain <= 100:
            return jsonify({"error": "expected_gain_pct -100 ile 100 arasinda olmalidir"}), 400
        if not 0 <= confidence <= 1:
            return jsonify({"error": "confidence_score 0 ile 1 arasinda olmalidir"}), 400

        pred = PredictionOpportunity(
            symbol=symbol,
            current_price=current_price,
            target_price=target_price,
            forecast_horizon=forecast_horizon,
            expected_gain_pct=expected_gain,
            confidence_score=confidence,
            trend_type=data.get("trend_type", "short_term"),
            source_model=data.get("source_model", "AIModel"),
            is_active=bool(data.get("is_active", True)),
            is_public=bool(data.get("is_public", True)),
            created_at=created_at,
        )
        db.session.add(pred)
        db.session.commit()
        add_audit_log(
            action_type="prediction_created",
            details={"symbol": pred.symbol},
            commit=True,
        )
        return jsonify(pred.to_dict()), 201
    except ValueError:
        # Sayısal alanlara yanlış tipte veri girilirse hata yakala
        return jsonify({"error": "Tip uyuşmazlığı: Lütfen sayısal alanlara geçerli bir değer girin."}), 400
    except Exception:
        db.session.rollback()
        logger.exception("Tahmin oluşturma hatası")
        return jsonify({"error": "Sunucu hatası"}), 500


@predictions_bp.route("/<int:prediction_id>", methods=["PATCH"])
@jwt_required()
@admin_required()
@require_csrf
def update_prediction(prediction_id):
    """Mevcut bir tahmin fırsatını kısmen günceller."""
    data = request.get_json() or {}
    pred = PredictionOpportunity.query.get_or_404(prediction_id)

    try:
        # Alan listeleri
        float_fields = ["current_price", "target_price", "expected_gain_pct", "confidence_score"]
        all_fields = [
            "symbol", "current_price", "target_price", "forecast_horizon",
            "expected_gain_pct", "confidence_score", "trend_type",
            "source_model", "is_active", "is_public"
        ]

        for field in all_fields:
            if field in data:
                value = data[field]
                if field in float_fields:
                    num = float(value)
                    if field in ["current_price", "target_price"] and num < 0:
                        return jsonify({"error": f"{field} negatif olamaz"}), 400
                    if field == "expected_gain_pct" and not -100 <= num <= 100:
                        return jsonify({"error": "expected_gain_pct -100 ile 100 arasinda olmalidir"}), 400
                    if field == "confidence_score" and not 0 <= num <= 1:
                        return jsonify({"error": "confidence_score 0 ile 1 arasinda olmalidir"}), 400
                    setattr(pred, field, num)
                elif field == "symbol":
                    sym = value.strip().upper()
                    if len(sym) > 20:
                        return jsonify({"error": "Symbol en fazla 20 karakter olabilir"}), 400
                    setattr(pred, field, sym)
                else:
                    setattr(pred, field, value)

        db.session.commit()
        add_audit_log(
            action_type="prediction_updated",
            target_id=prediction_id,
            details=data,
            commit=True,
        )
        return jsonify(pred.to_dict()), 200
    except ValueError:
        # Sayısal alanlara yanlış tipte veri girilirse hata yakala
        return jsonify({"error": "Tip uyuşmazlığı: Lütfen sayısal alanlara geçerli bir değer girin."}), 400
    except Exception:
        db.session.rollback()
        logger.exception("Tahmin güncelleme hatası")
        return jsonify({"error": "Sunucu hatası"}), 500


@predictions_bp.route("/<int:prediction_id>", methods=["DELETE"])
@jwt_required()
@admin_required()
@require_csrf
def delete_prediction(prediction_id):
    """Bir tahmin fırsatını siler."""
    pred = PredictionOpportunity.query.get_or_404(prediction_id)
    db.session.delete(pred)
    db.session.commit()
    add_audit_log(
        action_type="prediction_deleted",
        target_id=prediction_id,
        details={"symbol": pred.symbol},
        commit=True,
    )
    return jsonify({"message": "Tahmin fırsatı başarıyla silindi."}), 200


# Veri Toplama Planı (Düşük maliyetli güvenilir kaynaklar)
# Bu veri kaynakları ileride tahmin motoruna beslenecek

DATA_SOURCES = [
    {"type": "Fiyat/Grafik", "source": "CoinGecko API", "reliability": "High", "cost": "Free", "python_tool": "pycoingecko"},
    {"type": "Teknik Analiz", "source": "Kendin Hesapla", "reliability": "High", "cost": "Free", "python_tool": "pandas-ta"},
    {"type": "Haberler", "source": "RSS Beslemeleri", "reliability": "Mid-High", "cost": "Free", "python_tool": "feedparser"},
    {"type": "Haberler (Alternatif)", "source": "NewsAPI.org", "reliability": "High", "cost": "Free Tier", "python_tool": "requests"},
    {"type": "Haber & Yorum", "source": "CryptoPanic API", "reliability": "Mid-High", "cost": "Free Tier", "python_tool": "requests"},
    {"type": "Sosyal Etki", "source": "LunarCrush API", "reliability": "Mid", "cost": "Free Tier", "python_tool": "requests"},
    {"type": "Etkinlik Takvimi", "source": "CoinMarketCal", "reliability": "Mid", "cost": "Free", "python_tool": "requests"},
    {"type": "Yorum & Söylem", "source": "Messari News", "reliability": "High", "cost": "Free Tier", "python_tool": "requests"},
    {"type": "Haber", "source": "CoinTelegraph RSS", "reliability": "High", "cost": "Free", "python_tool": "feedparser"}
]

# Planlanan veri toplama görevleri (fonksiyon adları ve açıklamaları ile birlikte tanımlanacak)
# Bu fonksiyonlar ayrı görev dosyalarında zamanlanmış görevler olarak çalıştırılacaktır

# - fetch_price_data()      -> CoinGecko üzerinden fiyat verilerini alır
# - fetch_technical_data()  -> Teknik analiz verilerini üretir
# - fetch_news_rss()        -> RSS kaynaklarından haberleri çeker
# - fetch_news_api()        -> NewsAPI ve CryptoPanic gibi API'lerden haberleri toplar
# - fetch_social_signals()  -> LunarCrush gibi kaynaklardan sosyal etki sinyalleri çeker
# - fetch_event_calendar()  -> CoinMarketCal'den yaklaşan etkinlikleri alır
# - fetch_sentiment_news()  -> Messari gibi kaynaklardan yorumlu haberleri çeker


def fetch_price_data(symbol: str, vs_currency: str = "usd") -> dict:
    """CoinGecko API üzerinden fiyat verilerini döndürür."""
    import requests

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": symbol, "vs_currencies": vs_currency},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get(symbol, {})
    except Exception:  # pragma: no cover - dış servis hatası
        return {}


def fetch_technical_data(prices: list[float]) -> dict:
    """Basit teknik analiz indikatörlerini hesaplar (pandas-ta)."""
    try:  # pragma: no cover - isteğe bağlı kütüphane
        import pandas as pd
        import pandas_ta as ta
    except Exception:
        return {}

    if not prices:
        return {}

    df = pd.DataFrame(prices, columns=["close"])
    indicators = {
        "rsi": ta.rsi(df["close"]).iloc[-1],
        "macd": ta.macd(df["close"])["MACD_12_26_9"].iloc[-1],
    }
    return {k: float(v) for k, v in indicators.items() if v is not None}


def fetch_news_rss(urls: list[str]) -> list[dict]:
    """RSS kaynaklarından haber başlıklarını döndürür."""
    try:  # pragma: no cover - isteğe bağlı kütüphane
        import feedparser
    except Exception:
        return []

    articles: list[dict] = []
    for url in urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            articles.append({
                "title": entry.get("title"),
                "link": entry.get("link"),
            })
    return articles


def fetch_news_api(api_key: str, query: str, page_size: int = 10) -> list[dict]:
    """NewsAPI üzerinden haberleri alır."""
    import requests

    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "apiKey": api_key, "pageSize": page_size},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("articles", [])
    except Exception:  # pragma: no cover - dış servis hatası
        return []


def fetch_social_signals(symbol: str, api_key: str | None = None) -> dict:
    """LunarCrush API üzerinden sosyal sinyal verisi toplar."""
    import requests

    params = {"data": "assets", "symbol": symbol}
    if api_key:
        params["key"] = api_key
    try:
        resp = requests.get("https://api.lunarcrush.com/v2", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [{}])[0] if data.get("data") else {}
    except Exception:  # pragma: no cover - dış servis hatası
        return {}


def fetch_event_calendar(api_key: str, symbol: str) -> list[dict]:
    """CoinMarketCal API'inden yaklaşan etkinlikleri getirir."""
    import requests

    headers = {"x-api-key": api_key}
    try:
        resp = requests.get(
            "https://developers.coinmarketcal.com/v1/events",
            params={"symbols": symbol},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("body", [])
    except Exception:  # pragma: no cover - dış servis hatası
        return []


def fetch_sentiment_news(api_key: str, asset: str) -> list[dict]:
    """Messari News API'den duygu analizi yapılmış haberleri döndürür."""
    import requests

    try:
        resp = requests.get(
            "https://data.messari.io/api/v1/news",
            params={"assets": asset},
            headers={"x-messari-api-key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception:  # pragma: no cover - dış servis hatası
        return []

