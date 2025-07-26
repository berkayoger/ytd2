from flask import Blueprint, request, jsonify
from backend.db import db
from backend.models.plan import Plan
from backend.db.models import User, UserRole
from backend.utils.decorators import admin_required
import json
from datetime import datetime

plan_admin_bp = Blueprint("plan_admin_bp", __name__)

@plan_admin_bp.route("/admin/plans", methods=["GET"])
@admin_required
def list_plans():
    plans = Plan.query.all()
    if request.args.get("simple") == "1":
        return jsonify({"plans": [{"id": p.id, "name": p.name} for p in plans]})
    return jsonify([p.to_dict() for p in plans])

@plan_admin_bp.route("/admin/plans", methods=["POST"])
@admin_required
def create_plan():
    data = request.get_json() or {}
    features = data.get("features", {})
    plan = Plan(
        name=data["name"],
        price=data["price"],
        features=json.dumps(features),
        discount_price=data.get("discount_price"),
        discount_start=datetime.fromisoformat(data["discount_start"]) if data.get("discount_start") else None,
        discount_end=datetime.fromisoformat(data["discount_end"]) if data.get("discount_end") else None,
        is_public=data.get("is_public", True),
        is_active=data.get("is_active", True),
    )
    db.session.add(plan)
    db.session.commit()
    return jsonify(plan.to_dict()), 201

@plan_admin_bp.route("/admin/plans/<int:plan_id>", methods=["PUT"])
@admin_required
def update_plan(plan_id):
    plan = Plan.query.get_or_404(plan_id)
    data = request.get_json() or {}
    plan.name = data.get("name", plan.name)
    plan.price = data.get("price", plan.price)
    plan.is_active = data.get("is_active", plan.is_active)
    if "discount_price" in data:
        plan.discount_price = data["discount_price"]
    if "discount_start" in data:
        plan.discount_start = datetime.fromisoformat(data["discount_start"]) if data["discount_start"] else None
    if "discount_end" in data:
        plan.discount_end = datetime.fromisoformat(data["discount_end"]) if data["discount_end"] else None
    if "is_public" in data:
        plan.is_public = data.get("is_public", plan.is_public)
    if "features" in data:
        plan.features = json.dumps(data["features"])
    db.session.commit()
    return jsonify(plan.to_dict())

@plan_admin_bp.route("/admin/plans/<int:plan_id>", methods=["DELETE"])
@admin_required
def delete_plan(plan_id):
    plan = Plan.query.get_or_404(plan_id)
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"message": "Plan silindi"})

@plan_admin_bp.route("/admin/users/<int:user_id>/plan", methods=["PUT"])
@admin_required
def change_user_plan(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    plan_id = data.get("plan_id")
    plan = Plan.query.get_or_404(plan_id)
    user.plan_id = plan.id
    plan_roles = plan.features_dict().get("grants_roles", [])
    if plan_roles:
        user.role = UserRole[plan_roles[0]] if plan_roles[0] in UserRole.__members__ else user.role
    if "expire_at" in data:
        user.plan_expire_at = datetime.fromisoformat(data["expire_at"])
    db.session.commit()
    return jsonify(user.to_dict())


@plan_admin_bp.route("/admin/plan-automation/run", methods=["POST"])
@admin_required
def manual_automation():
    """Manually trigger plan automation tasks."""
    from backend.tasks.plan_tasks import (
        auto_downgrade_expired_plans,
        auto_expire_boosts,
        activate_pending_plans,
    )

    auto_downgrade_expired_plans.delay()
    auto_expire_boosts.delay()
    activate_pending_plans.delay()
    return jsonify({"ok": True})


@plan_admin_bp.route("/admin/plans/analytics", methods=["GET"])
@admin_required
def plan_analytics():
    stats = db.session.execute(
        "SELECT plan_id, COUNT(*) FROM users GROUP BY plan_id"
    )
    return jsonify([
        {"plan_id": row[0], "user_count": row[1]} for row in stats
    ])


@plan_admin_bp.route("/admin/users/<int:user_id>/recommend-plan", methods=["GET"])
@admin_required
def recommend_plan_api(user_id):
    user = User.query.get_or_404(user_id)
    usage = {"predictions": getattr(user, "prediction_count_last_30d", 0)}
    from backend.utils.plan_recommender import recommend_plan
    suggested = recommend_plan(user, usage)
    return jsonify({"suggested_plan": suggested})
