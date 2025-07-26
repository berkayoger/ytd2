from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from backend.auth.middlewares import admin_required
from backend.db import db
from backend.db.models import User, SubscriptionPlan, UserRole
import json
from werkzeug.security import generate_password_hash
import secrets


user_admin_bp = Blueprint("user_admin", __name__, url_prefix="/api/admin/users")


@user_admin_bp.route("/", methods=["POST"])
@jwt_required()
@admin_required()
def create_user():
    data = request.get_json() or {}

    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "user")
    plan = data.get("subscription_level", "Free")

    if not email or not password:
        return jsonify({"error": "E-posta ve şifre zorunludur"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Bu e-posta zaten kayıtlı"}), 409

    hashed_pw = generate_password_hash(password)
    api_key = secrets.token_hex(32)

    try:
        role_enum = UserRole[role.upper()]
    except KeyError:
        role_enum = UserRole.USER

    try:
        plan_enum = SubscriptionPlan[plan.upper()]
    except KeyError:
        plan_enum = SubscriptionPlan.TRIAL

    user = User(
        username=email,
        email=email,
        password_hash=hashed_pw,
        role=role_enum,
        subscription_level=plan_enum,
        api_key=api_key,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify(user.to_dict()), 201


@user_admin_bp.route("/", methods=["GET"])
@jwt_required()
@admin_required()
def list_users():
    email = request.args.get("email")
    role = request.args.get("role")
    plan = request.args.get("subscription_level")

    query = User.query

    if email:
        query = query.filter(User.email.ilike(f"%{email}%"))
    if role:
        query = query.filter(User.role == role)
    if plan:
        query = query.filter(User.subscription_level == plan)

    users = query.all()
    return jsonify([u.to_dict() for u in users])


@user_admin_bp.route("/<int:user_id>", methods=["PUT"])
@jwt_required()
@admin_required()
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}

    role = data.get("role")
    if role:
        try:
            user.role = UserRole[role.upper()]
        except KeyError:
            pass

    level = data.get("subscription_level")
    if level:
        try:
            user.subscription_level = SubscriptionPlan[level.upper()]
        except KeyError:
            pass

    if "is_active" in data:
        user.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify(user.to_dict())


@user_admin_bp.route("/<int:user_id>", methods=["DELETE"])
@jwt_required()
@admin_required()
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Kullanıcı silindi"})


@user_admin_bp.route("/<int:user_id>/custom-features", methods=["PUT"])
@jwt_required()
@admin_required()
def set_custom_features(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    user.custom_features = json.dumps(data.get("custom_features", {}))
    db.session.commit()
    return jsonify(user.to_dict())
