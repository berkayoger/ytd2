# File: backend/auth/routes.py

from flask import request, jsonify, current_app, g, render_template
from . import auth_bp  # Blueprint
from backend.db.models import (
    db,
    User,
    SubscriptionPlan,
    PasswordResetToken,
    UserSession,
)
from werkzeug.security import generate_password_hash, check_password_hash
from .jwt_utils import generate_tokens, verify_jwt, verify_csrf
from loguru import logger
from backend import limiter
from backend.utils.token_helper import generate_reset_token, verify_reset_token
from backend.utils.email import send_password_reset_email
from backend.utils.audit import log_action
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import uuid
import jwt

# Limiter instance from application factory

# Basit kayıt formu sayfası
@auth_bp.route('/register', methods=['GET'], endpoint='register')
def register_page():
    """Render the registration page."""
    return render_template('register.html')

@auth_bp.route('/register', methods=['POST'])
@limiter.limit("5/minute")
def register_user():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify(error="Kullanıcı adı ve şifre gerekli."), 400

    try:
        if User.query.filter_by(username=username).first():
            return jsonify(error="Kullanıcı adı zaten mevcut."), 409

        from backend.db.models import Role
        role = Role.query.filter_by(name='user').first()

        new_user = User(
            username=username,
            subscription_level=SubscriptionPlan.FREE,
            role_id=role.id if role else None
        )
        new_user.set_password(password)
        new_api_key = new_user.generate_api_key()

        db.session.add(new_user)
        db.session.commit()

        logger.info(f"Yeni kullanıcı kaydedildi: {username}")
        return jsonify(
            message="Kayıt başarılı.",
            username=username,
            api_key=new_api_key,
            subscription_level=new_user.subscription_level.value
        ), 201

    except Exception as e:
        logger.exception("Kayıt sırasında hata oluştu")
        db.session.rollback()
        return jsonify(error="Sunucu hatası. Lütfen daha sonra tekrar deneyin."), 500


@auth_bp.route('/login', methods=['POST'])
@limiter.limit("10/minute")
def login_user():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify(error="Kullanıcı adı ve şifre gerekli."), 400

    try:
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return jsonify(error="Geçersiz kullanıcı adı veya şifre."), 401

        access, refresh, csrf = generate_tokens(
            user.id, user.username, user.role.value
        )

        session = UserSession(
            user_id=user.id,
            refresh_token=generate_password_hash(refresh),
            expires_at=datetime.utcnow() + timedelta(days=current_app.config["REFRESH_TOKEN_EXP_DAYS"]),
        )
        db.session.add(session)
        db.session.commit()

        response = jsonify(
            message="Giriş başarılı.",
            username=username,
            api_key=user.api_key,
            subscription_level=user.subscription_level.value
        )
        secure = not current_app.debug
        max_age_access = current_app.config["ACCESS_TOKEN_EXP_MINUTES"] * 60
        max_age_refresh = current_app.config["REFRESH_TOKEN_EXP_DAYS"] * 86400

        # refreshToken ilk sırada yazılır ki testlerde headers.get('Set-Cookie')
        # çağrısı bu değeri yakalayabilsin
        response.set_cookie(
            "refreshToken", refresh,
            httponly=True, secure=secure, samesite="Strict", max_age=max_age_refresh
        )
        response.set_cookie(
            "accessToken", access,
            httponly=True, secure=secure, samesite="Strict", max_age=max_age_access
        )
        response.set_cookie(
            "csrf-token", csrf,
            httponly=False, secure=secure, samesite="Strict", max_age=max_age_refresh
        )

        logger.info(f"Kullanıcı girişi başarılı: {username}")
        log_action(user, action="login")
        return response

    except Exception:
        logger.exception("Giriş sırasında hata oluştu")
        return jsonify(error="Sunucu hatası. Lütfen daha sonra tekrar deneyin."), 500


@auth_bp.route('/refresh', methods=['POST'])
def refresh_tokens():
    token = request.cookies.get('refreshToken')
    if not token:
        return jsonify(error="Refresh token missing"), 401
    try:
        payload = jwt.decode(
            token,
            current_app.config["REFRESH_TOKEN_SECRET"],
            algorithms=["HS256"],
            issuer=current_app.config.get("JWT_ISSUER", "ytdcrypto"),
            audience=current_app.config.get("JWT_AUDIENCE", "ytdcrypto_users"),
        )
        user_id = int(payload.get("sub"))
    except jwt.PyJWTError:
        return jsonify(error="Invalid token"), 401

    session = UserSession.query.filter_by(user_id=user_id, revoked=False).first()
    if not session or not check_password_hash(session.refresh_token, token):
        return jsonify(error="Invalid token"), 401

    access, new_refresh, csrf = generate_tokens(user_id, payload.get("username"), payload.get("role"))
    session.refresh_token = generate_password_hash(new_refresh)
    session.expires_at = datetime.utcnow() + timedelta(days=current_app.config["REFRESH_TOKEN_EXP_DAYS"])
    db.session.commit()

    response = jsonify(message="Refreshed")
    secure = not current_app.debug
    max_age_access = current_app.config["ACCESS_TOKEN_EXP_MINUTES"] * 60
    max_age_refresh = current_app.config["REFRESH_TOKEN_EXP_DAYS"] * 86400
    # refreshToken once yazilmazsa testler ilk header'i okuyunca bu degeri
    # kacirabiliyor
    response.set_cookie(
        "refreshToken", new_refresh,
        httponly=True, secure=secure, samesite="Strict", max_age=max_age_refresh
    )
    response.set_cookie(
        "accessToken", access,
        httponly=True, secure=secure, samesite="Strict", max_age=max_age_access
    )
    response.set_cookie(
        "csrf-token", csrf,
        httponly=False, secure=secure, samesite="Strict", max_age=max_age_refresh
    )
    return response, 200


@auth_bp.route('/check-username', methods=['GET'])
@limiter.limit("30/minute")
def check_username_availability():
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify(error="Kullanıcı adı gerekli."), 400
    exists = bool(User.query.filter_by(username=username).first())
    return jsonify(available=not exists), 200


@auth_bp.route('/request_password_reset', methods=['POST'])
@limiter.limit("5/hour")
def request_password_reset():
    data = request.get_json() or {}
    identifier = data.get('identifier', '').strip()
    if not identifier:
        return jsonify(error="Kullanıcı adı veya e-posta gerekli."), 400

    try:
        user = User.query.filter_by(username=identifier).first()
        if not user:
            logger.warning(f"Şifre sıfırlama: kullanıcı bulunamadı: {identifier}")
            return jsonify(message="Şifre sıfırlama talimatları e-posta adresinize gönderildi."), 200

        existing = PasswordResetToken.query.filter_by(
            user_id=user.id, is_used=False
        ).filter(PasswordResetToken.expires_at > datetime.utcnow()).first()
        if existing:
            return jsonify(message="Zaten aktif bir şifre sıfırlama talimatı gönderildi."), 200

        token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(hours=1)
        reset = PasswordResetToken(
            user_id=user.id, reset_token=token,
            expires_at=expires_at, is_used=False
        )
        db.session.add(reset)
        db.session.commit()

        # E-posta işini Celery'ye devret
        current_app.extensions['celery'].send_task(
            'backend.tasks.send_reset_email', args=[user.email, token]
        )
        logger.info(f"Şifre sıfırlama token oluşturuldu: ID={user.id}")
        return jsonify(message="Şifre sıfırlama talimatları e-posta adresinize gönderildi."), 200

    except Exception:
        logger.exception("Şifre sıfırlama isteğinde hata oluştu")
        return jsonify(error="Sunucu hatası. Lütfen daha sonra tekrar deneyin."), 500


@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit("5/hour")
def forgot_password():
    data = request.get_json() or {}
    email = data.get('email')
    if not email:
        return jsonify({"error": "E-posta gerekli"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.is_active:
        return jsonify({"message": "Eğer hesap varsa, e-posta gönderildi."}), 200

    token = generate_reset_token(email)
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    reset_entry = PasswordResetToken(
        user_id=user.id,
        reset_token=token,
        expires_at=expires_at,
        is_used=False,
    )
    db.session.add(reset_entry)
    db.session.commit()

    send_password_reset_email(email, token)
    return jsonify({"message": "Eğer hesap varsa, e-posta gönderildi."}), 200


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json() or {}
    token = data.get('token')
    new_password = data.get('password')

    if not token or not new_password:
        return jsonify({"error": "Eksik veri"}), 400

    email = verify_reset_token(token)
    if not email:
        return jsonify({"error": "Geçersiz veya süresi dolmuş link"}), 400

    reset_entry = PasswordResetToken.query.filter_by(reset_token=token, is_used=False).first()
    if not reset_entry or reset_entry.expires_at < datetime.utcnow():
        return jsonify({"error": "Geçersiz veya süresi dolmuş link"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 404

    user.password_hash = generate_password_hash(new_password)
    reset_entry.is_used = True
    db.session.commit()
    log_action(user, action="password_reset")
    return jsonify({"message": "Şifre başarıyla güncellendi."}), 200
