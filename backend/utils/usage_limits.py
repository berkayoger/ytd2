from functools import wraps
from flask import g, request, jsonify, current_app
from datetime import datetime

from backend.db.models import UsageLimitModel, SubscriptionPlan, UsageLog


def check_usage_limit(feature_name):
    """Enforces daily and monthly usage limits for a feature."""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", None)
            if not user:
                api_key = request.headers.get("X-API-KEY")
                if api_key:
                    user = User.query.filter_by(api_key=api_key).first()
                    if user:
                        g.user = user
            if not user:
                return jsonify({"error": "Yetkilendirme hatası"}), 401

            plan_name = user.subscription_level.name.upper()

            # Premium veya sınırsız planlar için kısıtlama yok
            if plan_name in ["PREMIUM", "UNLIMITED"]:
                return f(*args, **kwargs)

            # Limiti veritabanından çek
            limit = UsageLimitModel.query.filter_by(
                plan_name=plan_name, feature=feature_name
            ).first()
            if not limit:
                return (
                    jsonify({"error": f"{feature_name} için kullanım limiti tanımlanmamış."}),
                    403,
                )

            redis_client = current_app.extensions.get("redis_client")
            if not redis_client:
                return jsonify({"error": "Rate kontrol altyapısı pasif."}), 500

            now = datetime.utcnow()
            day_key = f"usage:{user.id}:{feature_name}:day:{now.strftime('%Y%m%d')}"
            month_key = f"usage:{user.id}:{feature_name}:month:{now.strftime('%Y%m')}"

            daily_count = int(redis_client.get(day_key) or 0)
            monthly_count = int(redis_client.get(month_key) or 0)

            if limit.daily_limit is not None and daily_count >= limit.daily_limit:
                return (
                    jsonify({"error": f"Günlük limit aşıldı: {limit.daily_limit} / {feature_name}"}),
                    429,
                )

            if limit.monthly_limit is not None and monthly_count >= limit.monthly_limit:
                return (
                    jsonify({"error": f"Aylık limit aşıldı: {limit.monthly_limit} / {feature_name}"}),
                    429,
                )

            pipe = redis_client.pipeline()
            pipe.incr(day_key)
            pipe.expire(day_key, 86400)
            pipe.incr(month_key)
            pipe.expire(month_key, 2678400)
            pipe.execute()

            return f(*args, **kwargs)

        return wrapper

    return decorator


def get_usage_count(user, feature):
    """Return today's usage count for the given feature."""
    start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        UsageLog.query
        .filter_by(user_id=user.id, action=feature)
        .filter(UsageLog.timestamp >= start_of_day)
        .count()
    )
