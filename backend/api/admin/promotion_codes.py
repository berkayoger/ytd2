from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.db.models import db, PromotionCode

admin_promotion_bp = Blueprint("admin_promotion", __name__, url_prefix="/api/admin/promo")

@admin_promotion_bp.route("/", methods=["GET"])
@jwt_required()
@admin_required()
def list_promos():
    q = PromotionCode.query
    filter_val = request.args.get("filter")
    if filter_val:
        ilike = f"%{filter_val}%"
        q = q.filter((PromotionCode.code.ilike(ilike)) | (PromotionCode.description.ilike(ilike)))
    promos = q.order_by(PromotionCode.created_at.desc()).all()
    return jsonify({"promos": [p.to_dict() for p in promos]})

@admin_promotion_bp.route("/", methods=["POST"])
@jwt_required()
@admin_required()
def create_promo():
    data = request.get_json() or {}
    promo = PromotionCode(
        code=data.get("code", "").upper(),
        description=data.get("description"),
        promo_type=data.get("promo_type"),
        discount_type=data.get("discount_type"),
        discount_amount=data.get("discount"),
        feature=data.get("feature"),
        plans=data.get("plans"),
        usage_limit=data.get("usage_limit"),
        active_days=data.get("active_days"),
        validity_days=data.get("validity_days"),
        user_segment=data.get("user_segment"),
        custom_users=",".join(data.get("custom_users", [])) if isinstance(data.get("custom_users"), list) else data.get("custom_users"),
    )
    db.session.add(promo)
    db.session.commit()
    return jsonify({"ok": True, "promo": promo.to_dict()})

@admin_promotion_bp.route("/<int:promo_id>", methods=["DELETE"])
@jwt_required()
@admin_required()
def delete_promo(promo_id):
    promo = PromotionCode.query.get_or_404(promo_id)
    db.session.delete(promo)
    db.session.commit()
    return jsonify({"ok": True})

@admin_promotion_bp.route("/<int:promo_id>/toggle", methods=["POST"])
@jwt_required()
@admin_required()
def toggle_promo(promo_id):
    promo = PromotionCode.query.get_or_404(promo_id)
    promo.is_active = not promo.is_active
    db.session.commit()
    return jsonify({"ok": True, "is_active": promo.is_active})
