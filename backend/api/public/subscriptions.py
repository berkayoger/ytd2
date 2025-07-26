from flask import Blueprint, jsonify

subscriptions_bp = Blueprint("subscriptions", __name__, url_prefix="/api/subscriptions")

@subscriptions_bp.route("/", methods=["GET"])
def list_plans():
    plans = [
        {
            "name": "Ücretsiz",
            "price": 0,
            "features": [
                "Günlük 3 analiz görüntüleme",
                "Sınırlı coin erişimi",
                "Genel piyasa sinyalleri"
            ]
        },
        {
            "name": "Standart",
            "price": 149,
            "features": [
                "Günde 10+ analiz",
                "Tüm coin sinyalleri",
                "Kısa ve orta vadeli tahminler",
                "Temel analiz ve haberler"
            ]
        },
        {
            "name": "Pro",
            "price": 299,
            "features": [
                "Sınırsız analiz erişimi",
                "Uzun vadeli tahmin motoru",
                "Stratejik AI önerileri",
                "Portföy optimizasyon önerileri",
                "E-posta ile sinyal bildirimi"
            ]
        }
    ]
    return jsonify(plans)
