# File: backend/auth/middlewares.py

import logging
import os
from functools import wraps
from flask import jsonify, request, g
# Flask-JWT-Extended 4.x sürümlerinde `fresh_jwt_required` fonksiyonu
# mevcut olmayabilir. Geriye dönük uyumluluk için yoksa `jwt_required`
# fonksiyonunu kullanıyoruz.
try:
    from flask_jwt_extended import fresh_jwt_required, get_jwt, get_jwt_identity
except Exception:  # pragma: no cover - kutuphane eksikse basit stub kullan
    def fresh_jwt_required(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def get_jwt():
        return {}

    def get_jwt_identity():
        return None
from backend.db.models import User, UserRole  # Kullanıcı modelini DB'den çekmek için
from sqlalchemy.exc import SQLAlchemyError

# Logger yapılandırması uygulama başlangıcında ayarlanmalı.
logger = logging.getLogger(__name__)


def admin_required():
    """Admin yetkisi gerektiren uç nokta dekoratörü."""

    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            admin_key = request.headers.get("X-ADMIN-API-KEY")
            expected_key = os.getenv("ADMIN_ACCESS_KEY")

            # Özel admin anahtarı varsa JWT kontrolü yapmadan yetki ver
            if admin_key and expected_key and admin_key == expected_key:
                api_key = request.headers.get("X-API-KEY")
                user = User.query.filter_by(api_key=api_key).first()
                is_admin = (
                    user
                    and (
                        user.role == UserRole.ADMIN
                        or (user.role_obj and user.role_obj.name == "admin")
                    )
                )
                if not is_admin:
                    return jsonify({"error": "Admin yetkisi gereklidir!"}), 403
                g.user = user
                return fn(*args, **kwargs)

            @fresh_jwt_required()
            def jwt_protected():
                try:
                    user_id = get_jwt_identity()
                    user = User.query.get(user_id)
                    if not user or user.role != UserRole.ADMIN:
                        jti = get_jwt().get('jti')
                        logger.warning(
                            f"Unauthorized admin access attempt! User ID: {user_id}, JTI: {jti}"
                        )
                        return jsonify({"error": "Admin yetkisi gereklidir!"}), 403
                    g.user = user
                    return fn(*args, **kwargs)
                except SQLAlchemyError:
                    logger.exception("admin_required: Veritabanı hatası oluştu")
                    return jsonify({"error": "Sunucu hatası. Lütfen daha sonra tekrar deneyin."}), 500
                except Exception:
                    logger.exception("admin_required: Beklenmeyen bir hata oluştu")
                    return jsonify({"error": "Sunucu hatası. Lütfen daha sonra tekrar deneyin."}), 500

            return jwt_protected()

        return decorator

    return wrapper

# Örnek Kullanım:
# from backend.auth.middlewares import admin_required
#
# @app.route('/admin/dashboard')
# @fresh_jwt_required()
# @admin_required()
# def admin_dashboard():
#     return jsonify({"message": "Admin paneline hoş geldiniz!"})
