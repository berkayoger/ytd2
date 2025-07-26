from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.db.models import db, PromoCode, SubscriptionPlan
from datetime import datetime

admin_promo_bp = Blueprint("admin_promo", __name__, url_prefix="/api/admin/promo-codes")


@admin_promo_bp.route("/", methods=["GET"])
@jwt_required()
@admin_required()
def list_promo_codes():
    codes = PromoCode.query.order_by(PromoCode.created_at.desc()).all()
    return jsonify([c.to_dict() for c in codes]), 200


@admin_promo_bp.route("/", methods=["POST"])
@jwt_required()
@admin_required()
def create_promo_code():
    data = request.get_json() or {}
    try:
        expires_at = None
        expires_at_str = data.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
            except ValueError:
                return jsonify({"error": "Ge\u00e7ersiz tarih format\u0131 (expires_at)"}), 400

        user_email = data.get("user_email")
        if user_email == "":
            user_email = None
        assigned_user_id = data.get("assigned_user_id")

        code = PromoCode(
            code=data["code"].upper(),
            plan=SubscriptionPlan[data["plan"].upper()],
            duration_days=int(data["duration_days"]),
            max_uses=int(data["max_uses"]),
            expires_at=expires_at,
            user_email=user_email,
            assigned_user_id=assigned_user_id,
        )
        db.session.add(code)
        db.session.commit()
        return jsonify(code.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@admin_promo_bp.route("/user/<int:user_id>", methods=["GET"])
@jwt_required()
@admin_required()
def get_user_promos(user_id):
    promos = PromoCode.query.filter_by(assigned_user_id=user_id).all()
    return jsonify([p.to_dict() for p in promos]), 200


@admin_promo_bp.route("/<int:promo_id>", methods=["DELETE"])
@jwt_required()
@admin_required()
def delete_promo_code(promo_id):
    promo = PromoCode.query.get_or_404(promo_id)
    db.session.delete(promo)
    db.session.commit()
    return jsonify({"message": "Silindi"}), 200


@admin_promo_bp.route("/<int:promo_id>", methods=["PATCH"])
@jwt_required()
@admin_required()
def update_promo_code(promo_id):
    promo = PromoCode.query.get_or_404(promo_id)
    data = request.get_json() or {}
    try:
        if "max_uses" in data:
            promo.max_uses = int(data["max_uses"])
        if "duration_days" in data:
            promo.duration_days = int(data["duration_days"])
        if "is_active" in data:
            promo.is_active = bool(data["is_active"])
        if "user_email" in data:
            promo.user_email = data["user_email"] or None
        if "assigned_user_id" in data:
            promo.assigned_user_id = data["assigned_user_id"]
        if "expires_at" in data:
            if data["expires_at"]:
                try:
                    promo.expires_at = datetime.fromisoformat(data["expires_at"])
                except ValueError:
                    return jsonify({"error": "Ge\u00e7ersiz tarih format\u0131 (expires_at)"}), 400
            else:
                promo.expires_at = None
        db.session.commit()
        return jsonify(promo.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@admin_promo_bp.route("/<int:promo_id>/expiration", methods=["PATCH"])
@jwt_required()
@admin_required()
def update_promo_expiration(promo_id):
    promo = PromoCode.query.get_or_404(promo_id)
    data = request.get_json() or {}
    expires_at_str = data.get("expires_at")
    if not expires_at_str:
        return jsonify({"error": "expires_at field is required"}), 400
    try:
        new_date = datetime.fromisoformat(expires_at_str)
    except ValueError:
        return jsonify({"error": "Invalid ISO date"}), 400
    if new_date <= datetime.utcnow():
        return jsonify({"error": "Expiration must be in the future"}), 400
    try:
        promo.expires_at = new_date
        db.session.commit()
        return jsonify(promo.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400

