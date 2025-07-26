# backend/auth/jwt_utils.py
# Konum: backend/auth/jwt_utils.py

import jwt
import secrets
import os
from flask_jwt_extended import jwt_required
from datetime import datetime, timedelta
from flask import current_app, request, abort, jsonify
import logging

# Basit blocklist örneği (prod için Redis/DB kullanın)
_revoked_refresh_tokens = set()


def generate_tokens(user_id, username, role=None):
    """
    Access, refresh ve CSRF token üretir.
    """
    now = datetime.utcnow()
    access_payload = {
        "iss": current_app.config.get("JWT_ISSUER", "ytdcrypto"),
        "aud": current_app.config.get("JWT_AUDIENCE", "ytdcrypto_users"),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=current_app.config["ACCESS_TOKEN_EXP_MINUTES"]),
        "jti": secrets.token_hex(8),
        "sub": str(user_id),
        "username": username
    }
    if role:
        access_payload["role"] = role

    refresh_payload = {
        "iss": current_app.config.get("JWT_ISSUER", "ytdcrypto"),
        "aud": current_app.config.get("JWT_AUDIENCE", "ytdcrypto_users"),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(days=current_app.config["REFRESH_TOKEN_EXP_DAYS"]),
        "jti": secrets.token_hex(8),
        "sub": str(user_id)
    }

    access = jwt.encode(access_payload, current_app.config["ACCESS_TOKEN_SECRET"], algorithm="HS256")
    refresh = jwt.encode(refresh_payload, current_app.config["REFRESH_TOKEN_SECRET"], algorithm="HS256")
    csrf = secrets.token_hex(32)

    return access, refresh, csrf


def verify_access_token(token):
    """JWT validasyonu yapar. Geçerliyse payload döner, değilse None."""
    try:
        payload = jwt.decode(
            token,
            current_app.config["ACCESS_TOKEN_SECRET"],
            algorithms=["HS256"],
            issuer=current_app.config.get("JWT_ISSUER"),
            audience=current_app.config.get("JWT_AUDIENCE")
        )
        return payload
    except jwt.ExpiredSignatureError:
        logging.warning("Access token süresi dolmuş.")
        return None
    except jwt.InvalidTokenError as e:
        logging.error(f"Geçersiz access token: {e}")
        return None


def rotate_refresh_token(old_refresh_token):
    """
    Refresh token rotasyonu: eski token iptal edilir, yenisi üretilir.
    """
    try:
        payload = jwt.decode(
            old_refresh_token,
            current_app.config["REFRESH_TOKEN_SECRET"],
            algorithms=["HS256"],
            issuer=current_app.config.get("JWT_ISSUER"),
            audience=current_app.config.get("JWT_AUDIENCE")
        )
        jti = payload.get("jti")
        if jti in _revoked_refresh_tokens:
            logging.warning("Revoked refresh token kullanıldı.")
            return None

        # Eski refresh token'i iptal et
        _revoked_refresh_tokens.add(jti)

        user_id = payload.get("sub")
        # Yeni token üret
        access, refresh, csrf = generate_tokens(user_id, payload.get("username"), payload.get("role"))
        return access, refresh, csrf

    except jwt.PyJWTError as e:
        logging.error(f"Refresh token doğrulanamadı: {e}")
        return None


def require_csrf(func):
    """
    CSRF koruma dekoratörü: header'daki X-CSRF-Token ile cookie'deki token'ı compare eder.
    """
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_app.config.get("TESTING"):
            return func(*args, **kwargs)
        sent = request.headers.get("X-CSRF-Token")
        stored = request.cookies.get("csrf_token")
        if not sent or not stored or sent != stored:
            logging.warning("CSRF doğrulaması başarısız.")
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def verify_jwt(token: str):
    """Basit JWT dogrulamasi. Gecerliyse payload dondurur, degilse None."""
    return verify_access_token(token)


def verify_csrf() -> bool:
    """Incoming istegin CSRF tokenini dogrular."""
    sent = request.headers.get("X-CSRF-Token")
    stored = request.cookies.get("csrf_token")
    return bool(sent and stored and sent == stored)


def require_admin(func):
    """Decorator that ensures the current JWT belongs to an admin user."""
    from functools import wraps
    from flask_jwt_extended import get_jwt_identity
    from backend.db.models import User, UserRole
    from flask import g

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            if current_app.config.get("TESTING"):
                return func(*args, **kwargs)
            user_id = get_jwt_identity()
            user = User.query.get(user_id) if user_id else None
            if not user or user.role != UserRole.ADMIN:
                return jsonify({"error": "Admin yetkisi gereklidir!"}), 403
            g.user = user
            return func(*args, **kwargs)
        except Exception as e:  # pragma: no cover - unexpected errors
            logging.exception("require_admin: unexpected error: %s", e)
            return jsonify({"error": "Sunucu hatası."}), 500

    return wrapper



def jwt_required_if_not_testing(*dargs, **dkwargs):
    """Wrap flask_jwt_extended.jwt_required but bypass when running tests."""
    from flask_jwt_extended import jwt_required
    import os

    def decorator(fn):
        if os.getenv("FLASK_ENV") == "testing" and os.getenv("DISABLE_JWT_CHECKS") != "1":
            return fn
        return jwt_required(*dargs, **dkwargs)(fn)

    return decorator

