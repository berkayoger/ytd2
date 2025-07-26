from flask import request, jsonify, g
from loguru import logger
from flask_jwt_extended import jwt_required

from backend.auth.jwt_utils import require_csrf
from backend.middleware.plan_limits import enforce_plan_limit
from backend.services.decision_engine import generate_recommendation
from backend.utils.feature_flags import feature_flag_enabled
from backend.utils.usage_tracking import record_usage

from backend.core import core_bp


@core_bp.route("/predict", methods=["POST"])
@jwt_required()
@require_csrf
@enforce_plan_limit("predict_daily")
def predict():
    try:
        user = g.user
        data = request.get_json()
        coin = data.get("coin")
        profile = data.get("profile", "moderate")
        explain = data.get("explain", True)
        if not coin:
            return jsonify({"error": "Eksik veri: coin"}), 400

        result = generate_recommendation(coin, profile, explain, user)

        # Kullanım kaydı ekle
        record_usage(user, "predict_daily")

        return jsonify(result)
    except Exception:
        logger.exception("Predict hatası")
        return jsonify({"error": "Sunucu hatası"}), 500

