# backend/utils/decorators.py

from functools import wraps
from flask import g, jsonify, request
from loguru import logger
from backend.db.models import User, SubscriptionPlan, UserRole

def _error_response(message: str, status_code: int):
    """Hata yanıtları için merkezi bir yardımcı fonksiyon."""
    return jsonify({"error": message}), status_code


def admin_required(f):
    """Authorization header'ındaki API anahtarını kontrol eder."""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Token gerekli"}), 401
        if token.startswith("Bearer "):
            token = token.split(" ", 1)[1]
        user = User.query.filter_by(api_key=token).first()
        if not user or user.role not in [UserRole.ADMIN, UserRole.SYSTEM_ADMIN]:
            return jsonify({"error": "Yetkisiz erişim"}), 403
        return f(*args, **kwargs)

    return decorated

def require_role(required_role: UserRole):
    """
    Bir endpoint'e erişim için belirli bir kullanıcı rolünü zorunlu kılan bir decorator.
    
    Kullanım:
    @app.route('/admin')
    @require_role(UserRole.ADMIN)
    def admin_dashboard():
        return "Admin Paneli"
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Bu decorator'ın, JWT doğrulamasının yapıldığı bir middleware'den
            # sonra çalıştığını ve g.user'ın ayarlandığını varsayıyoruz.
            if not hasattr(g, 'user') or not isinstance(g.user, User):
                return _error_response("Yetkilendirme hatası: Kullanıcı bilgisi bulunamadı.", 401)
            
            # Kullanıcının rolünü kontrol et
            if g.user.role != required_role:
                logger.warning(
                    f"Yetkisiz erişim denemesi. Kullanıcı: {g.user.username}, Gerekli Rol: {required_role.name}"
                )
                return _error_response(f"Erişim yetkiniz yok. Gerekli rol: {required_role.name}", 403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_subscription_plan(minimum_plan: SubscriptionPlan):
    """
    Bir endpoint'e erişim için minimum bir abonelik seviyesini zorunlu kılan decorator.
    
    Kullanım:
    @app.route('/premium-feature')
    @require_subscription_plan(SubscriptionPlan.PREMIUM)
    def premium_feature():
        return "Bu bir premium özelliktir."
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(g, 'user') or not isinstance(g.user, User):
                api_key = request.headers.get('X-API-KEY')
                if api_key:
                    user = User.query.filter_by(api_key=api_key).first()
                    if user:
                        g.user = user
            if not hasattr(g, 'user') or not isinstance(g.user, User):
                return _error_response(
                    "Yetkilendirme hatası: Kullanıcı bilgisi bulunamadı.", 401
                )

            user_plan_level = g.user.subscription_level.value
            required_plan_level = minimum_plan.value

            # Kullanıcının aboneliğinin aktif olup olmadığını kontrol et
            if not g.user.is_subscription_active():
                logger.warning(
                    f"Kullanıcı {g.user.username} aktif olmayan abonelikle erişmeye çalıştı. Plan: {g.user.subscription_level.name}"
                )
                return _error_response("Aktif bir aboneliğiniz bulunmamaktadır.", 403)

            # Kullanıcının plan seviyesi, gerekli minimum seviyeden düşükse erişimi engelle
            if user_plan_level < required_plan_level:
                logger.warning(
                    f"Yetersiz abonelik seviyesi. Kullanıcı: {g.user.username}, Mevcut Plan: {g.user.subscription_level.name}, Gerekli Plan: {minimum_plan.name}"
                )
                return _error_response(f"Bu özelliğe erişim için en az '{minimum_plan.name.capitalize()}' abonelik planı gereklidir.", 403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
