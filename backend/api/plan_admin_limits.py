from flask import Blueprint, request, jsonify

from backend.auth.jwt_utils import require_csrf, require_admin
from flask_jwt_extended import jwt_required

from backend import db
from backend.models.plan import Plan
import json

plan_admin_limits_bp = Blueprint(
    "plan_admin_limits",
    __name__,
    url_prefix="/api/plans",
)


@plan_admin_limits_bp.route("/<int:plan_id>/update-limits", methods=["POST"])

@jwt_required()

@require_csrf
@require_admin
def update_plan_limits(plan_id):
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({"error": "Plan bulunamadı."}), 404

        new_limits = request.get_json()
        if not isinstance(new_limits, dict):
            return jsonify({"error": "Limit verileri geçersiz."}), 400

        for key, val in new_limits.items():
            if not isinstance(val, int) or val < 0:
                return jsonify({"error": f"'{key}' için geçersiz limit değeri."}), 400

        old_limits = json.loads(plan.features or "{}")

        plan.features = json.dumps(new_limits)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Plan limitleri güncellendi.",
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "features": new_limits,
                    "old_features": old_limits,
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@plan_admin_limits_bp.route("/all", methods=["GET"])

@jwt_required()

@require_csrf
@require_admin
def get_all_plans():
    try:
        plans = Plan.query.all()
        data = [
            {
                "id": plan.id,
                "name": plan.name,
                "features": json.loads(plan.features or "{}"),
            }
            for plan in plans
        ]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@plan_admin_limits_bp.route("/create", methods=["POST"])

@jwt_required()

@require_csrf
@require_admin
def create_plan():

    """Create a new plan with optional feature limits."""

    try:
        payload = request.get_json()
        name = payload.get("name") if payload else None
        price = payload.get("price", 0.0) if payload else 0.0
        features = payload.get("features", {}) if payload else {}

        if not name or not isinstance(features, dict):
            return jsonify({"error": "Geçersiz plan verileri"}), 400

        for key, val in features.items():
            if not isinstance(val, int) or val < 0:
                return jsonify({"error": f"'{key}' için geçersiz limit değeri."}), 400

        plan = Plan(name=name, price=price, features=json.dumps(features))
        db.session.add(plan)
        db.session.commit()

        return jsonify(plan.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@plan_admin_limits_bp.route("/<int:plan_id>", methods=["DELETE"])

@jwt_required()

@require_csrf
@require_admin
def delete_plan(plan_id):
    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({"error": "Plan bulunamadı."}), 404

        db.session.delete(plan)
        db.session.commit()
        return jsonify({"success": True, "message": "Plan silindi."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
