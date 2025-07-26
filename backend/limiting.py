from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import g, request
from backend.db.models import User

limiter = Limiter(get_remote_address)


def get_plan_rate_limit():
    api_key = request.headers.get("X-API-KEY")
    user = None
    if api_key:
        user = User.query.filter_by(api_key=api_key).first()
    if not user or not user.plan:
        return "30/minute"
    limits = user.plan.features_dict()
    return f"{limits.get('api_rate_limit_per_minute', 30)}/minute"
