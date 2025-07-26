import json
"""Utilities for enforcing plan limits on users."""

from datetime import datetime, timedelta
from flask import g, jsonify, request
from backend.db.models import UsageLog
import json


def get_limit_status(user, limit_name, usage_value):
    """Return limit status for a user feature usage."""
    limits = user.plan.features_dict() if user.plan else {}
    if getattr(user, "boost_expire_at", None) and user.boost_expire_at > datetime.utcnow():
        try:
            limits.update(json.loads(user.boost_features or "{}"))
        except Exception:
            pass
    if getattr(user, "custom_features", None):
        try:
            limits.update(json.loads(user.custom_features or "{}"))
        except Exception:
            pass
    max_value = limits.get(limit_name)
    if not max_value:
        return "unlimited"
    try:
        ratio = float(usage_value) / float(max_value)
    except ZeroDivisionError:
        return "limit_exceeded"
    if ratio >= 1:
        return "limit_exceeded"
    elif ratio >= 0.8:
        return "limit_warning"
    return "ok"


def get_user_effective_limits(user):
    """Kullanıcının plan, boost ve özel tanımlarını birleştirir."""

    limits: dict = {}

    # 3. Plan limitleri (en düşük öncelik)
    if user.plan and getattr(user.plan, "features", None):
        features = user.plan.features
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except Exception:
                features = {}
        limits.update(features)

    # 2. Geçici boost limitleri
    if getattr(user, "boost_features", None) and getattr(user, "boost_expire_at", None):
        if user.boost_expire_at > datetime.utcnow():
            try:
                boosts = json.loads(user.boost_features) if isinstance(user.boost_features, str) else user.boost_features
                limits.update(boosts)
            except Exception:
                pass

    # 1. Kullanıcıya özel limitler
    if getattr(user, "custom_features", None):
        try:
            custom = json.loads(user.custom_features) if isinstance(user.custom_features, str) else user.custom_features
            limits.update(custom)
        except Exception:
            pass

    return limits


def check_custom_feature(user, key):
    """Belirli bir özelliğin kullanıcıya tanımlı olup olmadığını kontrol eder."""
    try:
        features = json.loads(user.custom_features) if isinstance(user.custom_features, str) else user.custom_features
        return features.get(key, False)
    except Exception:
        return False


def give_user_boost(user, features, expire_at):
    user.boost_features = json.dumps(features)
    user.boost_expire_at = expire_at
    from backend import db
    db.session.commit()


PLAN_LIMITS = {
    "basic": {
        "predict_daily": 10,
        "api_request_daily": 100,
    },
    "premium": {
        "predict_daily": 100,
        "api_request_daily": 1000,
    },
}


def enforce_plan_limits(limit_key):
    def wrapper(fn):
        def inner(*args, **kwargs):
            user = g.user if hasattr(g, "user") else None
            if not user:
                api_key = request.headers.get("X-API-KEY")
                if api_key:
                    from backend.db.models import User
                    user = User.query.filter_by(api_key=api_key).first()
                    if user:
                        g.user = user
            if not user:
                return jsonify({"error": "Auth required"}), 401

            plan_name = (
                user.plan.name.lower() if getattr(user, "plan", None) else "basic"
            )
            limits = PLAN_LIMITS.get(plan_name, {})
            limit = limits.get(limit_key)

            if limit is None:
                return fn(*args, **kwargs)

            start_time = datetime.utcnow() - timedelta(days=1)
            usage_count = (
                UsageLog.query.filter_by(user_id=user.id, action=limit_key)
                .filter(UsageLog.timestamp > start_time)
                .count()
            )

            if usage_count >= limit:
                return (
                    jsonify(
                        {
                            "error": "PlanLimitExceeded",
                            "message": f"{plan_name} plan\u0131 i\u00e7in '{limit_key}' limiti ({limit}) a\u015f\u0131ld\u0131."
                        }
                    ),
                    429,
                )

            log = UsageLog(user_id=user.id, action=limit_key, timestamp=datetime.utcnow())
            from backend import db
            db.session.add(log)
            db.session.commit()

            return fn(*args, **kwargs)

        return inner

    return wrapper
