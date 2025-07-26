from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.db.models import db, UsageLimitModel

admin_usage_bp = Blueprint(
    "admin_usage",
    __name__,
    url_prefix="/api/admin/usage-limits",
)


@admin_usage_bp.route("/", methods=["GET"])
@jwt_required()
@admin_required()
def get_limits():
    limits = UsageLimitModel.query.all()
    return jsonify([limit.to_dict() for limit in limits]), 200


@admin_usage_bp.route("/", methods=["POST"])
@jwt_required()
@admin_required()
def create_limit():
    data = request.get_json() or {}
    try:
        limit = UsageLimitModel(
            plan_name=data["plan_name"],
            feature=data["feature"],
            daily_limit=int(data["daily_limit"]),
            monthly_limit=int(data["monthly_limit"]),
        )
        db.session.add(limit)
        db.session.commit()
        return jsonify(limit.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@admin_usage_bp.route("/<int:limit_id>", methods=["PATCH"])
@jwt_required()
@admin_required()
def update_limit(limit_id):
    data = request.get_json() or {}
    limit = UsageLimitModel.query.get_or_404(limit_id)
    try:
        if "daily_limit" in data:
            limit.daily_limit = int(data["daily_limit"])
        if "monthly_limit" in data:
            limit.monthly_limit = int(data["monthly_limit"])
        db.session.commit()
        return jsonify(limit.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@admin_usage_bp.route("/<int:limit_id>", methods=["DELETE"])
@jwt_required()
@admin_required()
def delete_limit(limit_id):
    limit = UsageLimitModel.query.get_or_404(limit_id)
    db.session.delete(limit)
    db.session.commit()
    return jsonify({"message": "Silindi"}), 200
