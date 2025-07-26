from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from backend.auth.middlewares import admin_required
from backend.db import db
from backend.db.models import (
    User,
    LoginAttempt,
    PaymentTransactionLog,
    PredictionOpportunity,
    SystemEvent,
)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/admin/analytics")


@analytics_bp.route("/summary", methods=["GET"])
@jwt_required()
@admin_required()
def summary():
    start_str = request.args.get("from")
    end_str = request.args.get("to")
    try:
        start = datetime.fromisoformat(start_str) if start_str else datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        return jsonify({"error": "invalid from"}), 400
    try:
        end = datetime.fromisoformat(end_str) if end_str else datetime.utcnow()
    except ValueError:
        return jsonify({"error": "invalid to"}), 400

    active_users = db.session.query(func.count(func.distinct(LoginAttempt.user_id))).filter(
        LoginAttempt.success.is_(True),
        LoginAttempt.created_at.between(start, end),
    ).scalar() or 0

    new_signups = db.session.query(func.count(User.id)).filter(
        User.created_at.between(start, end)
    ).scalar() or 0

    payment_count = db.session.query(func.count(PaymentTransactionLog.id)).filter(
        PaymentTransactionLog.created_at.between(start, end),
        PaymentTransactionLog.status == "success",
    ).scalar() or 0

    churned = db.session.query(func.count(User.id)).filter(
        User.is_active.is_(False)
    ).scalar() or 0

    return jsonify(
        {
            "active_users": active_users,
            "new_signups": new_signups,
            "successful_payments": payment_count,
            "churned_users": churned,
        }
    )


@analytics_bp.route("/plans", methods=["GET"])
@jwt_required()
@admin_required()
def plan_distribution():
    stats = db.session.query(
        User.subscription_level,
        func.count(User.id),
    ).group_by(User.subscription_level).all()
    result = [
        {"plan": level.name if level else "Unknown", "count": count}
        for level, count in stats
    ]
    return jsonify(result)


@analytics_bp.route("/usage", methods=["GET"])
@jwt_required()
@admin_required()
def usage_stats():
    total_predictions = db.session.query(func.count(PredictionOpportunity.id)).scalar() or 0
    total_events = db.session.query(func.count(SystemEvent.id)).scalar() or 0
    return jsonify({"predictions": total_predictions, "system_events": total_events})
