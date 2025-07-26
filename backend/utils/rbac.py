# backend/utils/rbac.py

from functools import wraps
from flask import g, jsonify, request
from loguru import logger

from backend.db.models import User, AlarmSeverityEnum
from backend.utils.helpers import is_user_accessible, add_audit_log

def _error_response(message: str, status_code: int, error_code: str = "AUTHORIZATION_ERROR"):
    """
    Hata yanıtları için merkezi ve yapılandırılmış bir yardımcı fonksiyon.
    """
    return jsonify({"error": {"code": error_code, "message": message}}), status_code

def _get_client_ip() -> str:
    """Gerçek istemci IP’sini elde et."""
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        # Çoklu IP listesi varsa ilkini al
        return xff.split(',')[0].strip()
    return request.remote_addr or "unknown"

def user_has_permission(user: User, permission_name: str) -> bool:
    """
    Kullanıcının belirtilen izne sahip olup olmadığını kontrol eder.
    İstek başına bir kez hesaplayıp önbellekler.
    """
    if not user or not user.role_obj:
        return False

    if not hasattr(g, '_permission_set'):
        # Burada joinedload ile ilişkili izinleri önceden çekmek performansı artırır
        g._permission_set = {p.name.lower() for p in user.role_obj.permissions}

    return permission_name.lower().strip() in g._permission_set

def require_permission(permission_name: str):
    """
    Bir uç noktanın çalıştırılabilmesi için gerekli izni kontrol eden decorator.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1) Temel kullanıcı erişilebilirlik kontrolü
            if not hasattr(g, 'user') or not isinstance(g.user, User) or not is_user_accessible(g.user):
                return _error_response(
                    "Yetkilendirme hatası: Geçersiz veya erişilemez kullanıcı.",
                    401,
                    "INVALID_USER"
                )

            # 2) İzin kontrolü
            if not user_has_permission(g.user, permission_name):
                ip = _get_client_ip()

                # Eğer bu istekte daha önce eklenmemişse denetim günlüğü yaz
                if not getattr(g, '_permission_denied_logged', False):
                    logger.warning(
                        "Unauthorized access attempt | user_id={} username={} ip_address={} required_permission={}",
                        g.user.id, g.user.username, ip, permission_name
                    )

                    add_audit_log(
                        action_type="PERMISSION_DENIED",
                        actor_id=g.user.id,
                        actor_username=g.user.username,
                        details={
                            "required_permission": permission_name,
                            "endpoint": request.path
                        },
                        ip_address=ip,
                        commit=True
                    )

                    # Tekrarlamayı önlemek için flag koy
                    g._permission_denied_logged = True

                return _error_response(
                    f"Bu işlemi gerçekleştirmek için '{permission_name}' yetkisine sahip olmalısınız.",
                    403,
                    "PERMISSION_DENIED"
                )

            # 3) İzin varsa devam et
            return f(*args, **kwargs)
        return decorated_function
    return decorator
