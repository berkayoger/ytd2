from flask import Blueprint, jsonify, g
from flask_jwt_extended import jwt_required
from backend.auth.jwt_utils import require_csrf
from backend.utils.usage_limits import get_usage_count
import json

limits_bp = Blueprint("limits", __name__, url_prefix="/api/limits")


@limits_bp.route("/status", methods=["GET"])
@jwt_required()
@require_csrf
def get_limit_status():
    user = g.user
    features = user.plan.features
    if isinstance(features, str):
        try:
            features = json.loads(features)
        except Exception:
            return jsonify({"error": "Plan özellikleri okunamadı."}), 500

    result = {}
    for key, limit in features.items():
        used = get_usage_count(user, key)
        remaining = max(limit - used, 0)
        percent = int((used / limit) * 100) if limit > 0 else 0
        result[key] = {
            "limit": limit,
            "used": used,
            "remaining": remaining,
            "percent_used": percent,
        }

    return jsonify({"limits": result})
