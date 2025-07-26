from flask import request, jsonify, g
from functools import wraps
from backend.db.models import User, UserRole
import json


def enforce_plan_limit(limit_key):
    """Decorator to enforce subscription plan feature limits."""

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = getattr(request, "current_user", None) or getattr(g, "user", None)
            if not user:
                api_key = request.headers.get("X-API-KEY")
                if api_key:
                    user = User.query.filter_by(api_key=api_key).first()
                    if user:
                        g.user = user
            if not user or not user.plan or not user.plan.features:
                return jsonify({"error": "Abonelik planı bulunamadı."}), 403

            user_role = getattr(user, "role", None)
            if user_role in [UserRole.ADMIN, UserRole.SYSTEM_ADMIN]:
                return f(*args, **kwargs)

            features = user.plan.features
            if isinstance(features, str):
                try:
                    features = json.loads(features)
                except Exception:
                    return jsonify({"error": "Plan özellikleri okunamadı."}), 500

            limit = features.get(limit_key)
            if limit is None:
                return jsonify({"error": f"{limit_key} limiti tanımlı değil."}), 403

            current_count = user.get_usage_count(limit_key)
            if current_count >= limit:
                return jsonify({"error": f"{limit_key} limiti aşıldı. ({limit})"}), 429

            return f(*args, **kwargs)

        return wrapped

    return decorator
