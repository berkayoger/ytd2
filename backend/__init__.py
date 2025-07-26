# backend/__init__.py

import os
from datetime import timedelta, datetime
from flask import Flask, jsonify, request, g
from flask_sqlalchemy import SQLAlchemy
from backend.db import db as base_db
from flask_cors import CORS
from backend.limiting import limiter
from flask_limiter.util import get_remote_address
from celery import Celery
from flask_socketio import SocketIO, emit
from flask.testing import FlaskClient
from backend.db.models import User, SubscriptionPlan
from backend.models.plan import Plan
from backend.utils.usage_limits import check_usage_limit
from loguru import logger
from redis import Redis
from sqlalchemy import text  # Veritabanı sorgusu için text fonksiyonu
import sys  # sys.exit için

# Dotenv yüklemesi uygulamanın en başında olmalı
from dotenv import load_dotenv

load_dotenv()

# Redis bağlantı ayarı
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# Uygulama konfigürasyonlarını içeren sınıf
class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///ytd_crypto.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_SESSION_OPTIONS = {"expire_on_commit": False}
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    }
    # Celery Broker ve Backend URL'leri Redis bağlantısının durumuna göre ayarlanır
    REDIS_URL = REDIS_URL
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_TIMEZONE = "Europe/Istanbul"

    # JWT Gizli Anahtarı (Ortam değişkeninden al, yoksa varsayılan güvenli olmayan bir değer kullan)
    # Üretimde bu anahtar çok güçlü ve güvenli tutulmalıdır.
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY", "super-secret-jwt-key-change-this-in-prod!"
    )
    ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET", "change_me_access")
    REFRESH_TOKEN_SECRET = os.getenv("REFRESH_TOKEN_SECRET", "change_me_refresh")
    ACCESS_TOKEN_EXP_MINUTES = int(os.getenv("ACCESS_TOKEN_EXP_MINUTES", "15"))
    REFRESH_TOKEN_EXP_DAYS = int(os.getenv("REFRESH_TOKEN_EXP_DAYS", "7"))
    # Price data caching süresi (saniye). Testlerde varsayılan 0'dır.
    PRICE_CACHE_TTL = int(os.getenv("PRICE_CACHE_TTL", "300"))
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # Celery Beat için periyodik görevlerin tanımlanması
    CELERY_BEAT_SCHEDULE = {
        "auto-analyze-bitcoin-every-15-minutes": {
            "task": "backend.tasks.celery_tasks.analyze_coin_task",
            "schedule": timedelta(minutes=15),
            "args": ("bitcoin", "moderate"),
            "options": {"queue": "default"},
        },
        "auto-analyze-ethereum-every-15-minutes": {
            "task": "backend.tasks.celery_tasks.analyze_coin_task",
            "schedule": timedelta(minutes=15),
            "args": ("ethereum", "moderate"),
            "options": {"queue": "default"},
        },
        "check-and-downgrade-subscriptions-daily": {
            "task": "backend.tasks.celery_tasks.check_and_downgrade_subscriptions",
            "schedule": timedelta(days=1),
            "options": {"queue": "default"},
        },
        'auto-downgrade-plans-everyday': {
            'task': 'backend.tasks.plan_tasks.auto_downgrade_expired_plans',
            'schedule': timedelta(days=1),
            'options': {'queue': 'default'},
        },
        'auto-expire-boosts-everyday': {
            'task': 'backend.tasks.plan_tasks.auto_expire_boosts',
            'schedule': timedelta(days=1),
            'options': {'queue': 'default'},
        },
    }
    # CORS Origins ayarı .env dosyasından
    # supports_credentials=True ise origins ASLA '*' olmamalıdır.
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:80,http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    # Frontend'in çalıştığı tüm geçerli domainler/portlar buraya virgülle ayrılmış olarak eklenmeli.

    # Ortam değişkeni (geliştirme/üretim)
    ENV = os.getenv("FLASK_ENV", "development")

    @staticmethod
    def assert_production_jwt_key():
        """
        Üretim ortamında güvenli bir JWT_SECRET_KEY'in ayarlı olduğunu doğrular.
        Uygulama başlamadan önce çağrılmalıdır.
        """
        if Config.ENV == "production" and (
            not Config.JWT_SECRET_KEY
            or Config.JWT_SECRET_KEY.startswith("super-secret")
        ):
            logger.critical(
                "🚨 KRİTİK HATA: Üretim ortamında varsayılan, boş veya güvensiz JWT_SECRET_KEY kullanılamaz! Lütfen '.env' dosyanızı kontrol edin."
            )
            sys.exit(1)  # Uygulamayı başlatmayı durdur

    @staticmethod
    def assert_production_cors_origins():
        """
        Üretim ortamında CORS originlerinin güvenli olduğunu doğrular.
        """
        if Config.ENV == "production" and (
            "*" in Config.CORS_ORIGINS or len(Config.CORS_ORIGINS) == 0
        ):
            logger.critical(
                "🚨 KRİTİK HATA: Üretim ortamında CORS origins '*' içeremez veya boş olamaz! Lütfen '.env' dosyanızı kontrol edin."
            )
            sys.exit(1)


# Flask uzantılarını global olarak başlat
db = base_db
celery_app = Celery()
socketio = SocketIO()


class LegacyTestClient(FlaskClient):
    """Compat shim for Werkzeug 2.x set_cookie signature."""

    def set_cookie(self, *args, **kwargs):
        if len(args) == 3 and "domain" not in kwargs:
            domain, key, value = args
            return super().set_cookie(key, value, domain=domain, **kwargs)
        return super().set_cookie(*args, **kwargs)


def create_app():
    app = Flask(__name__)
    app.test_client_class = LegacyTestClient

    app.config.from_object(Config)

    # Test ortamında varsayılan Postgres bağlantısını kullanma
    if os.getenv("FLASK_ENV") == "testing":
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        # SQLite memory veritabanı için pool ayarını minimize et
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False}
        }
        # Cache TTL testlerde 0 olmalı (cache pasif)
        app.config["PRICE_CACHE_TTL"] = int(os.getenv("PRICE_CACHE_TTL", "0"))

    # Üretim ortamı güvenlik doğrulamaları
    Config.assert_production_jwt_key()
    Config.assert_production_cors_origins()

    # CORS'u uygulamaya bağla. supports_credentials=True ise origins ASLA '*' olmamalıdır.
    # Güvenli bir CORS politikası için CORS_ORIGINS'i doğru şekilde ayarlayın.
    CORS(app, supports_credentials=True, origins=Config.CORS_ORIGINS)

    # Uzantıları uygulamaya bağla
    db.init_app(app)
    limiter.init_app(app)
    celery_app.conf.update(app.config)
    # SocketIO'nun cors_allowed_origins'ı Flask-CORS ile senkronize olmalı
    socketio.init_app(
        app,
        message_queue=Config.CELERY_BROKER_URL,
        cors_allowed_origins=Config.CORS_ORIGINS,
    )

    # Uygulama bağlamında veritabanı tablolarını oluştur
    # Bu satır sadece ilk defa çalıştırıldığında veya test ortamında kullanılmalı.
    # Üretimde 'flask db upgrade' komutları ile migration yapılmalıdır.
    with app.app_context():
        # Sadece geliştirme/test ortamında otomatik tablo oluştur.
        # Production için migration scriptleri kullanılmalıdır.
        if app.config["ENV"].lower() != "production":  # ENV değeri küçük harfe çevrildi
            db.create_all()
            # Testlerde gerekli olan temel roller ve izinler yoksa oluştur
            from backend.db.models import Role, Permission

            if not Role.query.filter_by(name="user").first():
                user_role = Role(name="user")
                admin_role = Role(name="admin")
                db.session.add_all([user_role, admin_role])
                db.session.commit()
            if not Permission.query.filter_by(name="admin_access").first():
                perm = Permission(name="admin_access")
                db.session.add(perm)
                db.session.commit()
                admin_role = Role.query.filter_by(name="admin").first()
                admin_role.permissions.append(perm)
                db.session.commit()
        else:
            logger.info(
                "Üretim ortamı: Otomatik db.create_all() atlandı. Migrasyonların uygulandığından emin olun."
            )

    # Uzantı nesnelerini app.extensions'a ekle, böylece Blueprint'lerden ve current_app'ten erişilebilir.
    # Bu, çoklu worker/proses ortamında tutarlı erişim sağlar.
    app.extensions["db"] = db
    app.extensions["limiter"] = limiter
    app.extensions["celery"] = celery_app
    app.extensions["socketio"] = socketio
    app.extensions["redis_client"] = Redis.from_url(app.config.get("REDIS_URL"))

    # Analiz sistemi uygulamaya bağlanır. Testlerde gerçek bağımlılıklar
    # yerine boş bir nesne atanır ki monkeypatch ile kolayca kullanılsın.
    if os.getenv("FLASK_ENV") == "testing":
        from types import SimpleNamespace

        app.ytd_system_instance = SimpleNamespace(collector=None, ai=None, engine=None)
    else:
        from backend.core.services import YTDCryptoSystem

        app.ytd_system_instance = YTDCryptoSystem()

    # Blueprint'leri kaydet
    from backend.auth.routes import auth_bp
    from backend.api.routes import api_bp
    from backend.admin_panel.routes import admin_bp
    from backend.api.plan_routes import plan_bp
    from backend.api.admin.plans import plan_admin_bp
    from backend.api.plan_admin_limits import plan_admin_limits_bp
    from backend.api.admin.usage_limits import admin_usage_bp
    from backend.api.admin.promo_codes import admin_promo_bp
    from backend.api.admin.promotion_codes import admin_promotion_bp
    from backend.api.admin.promo_stats import stats_bp
    from backend.api.admin.predictions import predictions_bp
    from backend.api.admin.users import user_admin_bp
    from backend.api.admin.audit import audit_bp
    from backend.api.admin.backup import backup_bp
    from backend.api.admin.system_events import events_bp
    from backend.api.admin.analytics import analytics_bp
    from backend.limits.routes import limits_bp
    from backend.api.ta_routes import bp as ta_bp
    from backend.api.public.technical import technical_bp
    from backend.api.public.subscriptions import subscriptions_bp

    # APScheduler tabanli gorevleri istege bagli olarak baslat
    if os.getenv("ENABLE_SCHEDULER", "0") == "1":
        from backend.api.admin import prediction_scheduler  # noqa: F401

 
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(plan_admin_limits_bp)
    app.register_blueprint(plan_bp, url_prefix='/api')
    app.register_blueprint(plan_admin_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(admin_usage_bp)
    app.register_blueprint(admin_promo_bp)
    app.register_blueprint(admin_promotion_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(predictions_bp)
    app.register_blueprint(user_admin_bp)
    app.register_blueprint(audit_bp, url_prefix='/api')
    app.register_blueprint(backup_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(ta_bp)
    app.register_blueprint(technical_bp)
    app.register_blueprint(subscriptions_bp)
    app.register_blueprint(limits_bp)

    # Sağlık Kontrol Endpoint'i
    @app.route("/health", methods=["GET"])
    def health_check():
        db_status = "ok"
        redis_status = "ok"

        try:
            with app.app_context():  # DB bağlantısını uygulama bağlamı içinde test et
                db.session.execute(text("SELECT 1"))
        except Exception as e:
            db_status = f"error: {e}"
            logger.error(f"Health check DB hatası: {e}")
            # Kritik hata durumunda alarma devret
            from backend.utils.alarms import send_security_alert_task

            send_security_alert_task.delay(
                "Veritabanı Bağlantı Hatası",
                {
                    "username": "Sistem",
                    "ip_address": request.remote_addr if request else "N/A",
                },
                f"Veritabanı bağlantısı kurulamıyor: {e}",
                severity="FATAL",
            )

        try:
            # Redis client başlangıçta kontrol edildiği için burada sadece ping yapıyoruz.
            app.extensions["redis_client"].ping()
        except Exception as e:
            redis_status = f"error: {e}"
            logger.error(f"Health check Redis hatası: {e}")
            # Kritik hata durumunda alarma devret
            from backend.utils.alarms import send_security_alert_task

            send_security_alert_task.delay(
                "Redis Bağlantı Hatası",
                {
                    "username": "Sistem",
                    "ip_address": request.remote_addr if request else "N/A",
                },
                f"Redis bağlantısı kurulamıyor: {e}",
                severity="FATAL",
            )

        overall_status = (
            "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
        )

        return (
            jsonify(
                {
                    "status": overall_status,
                    "database": db_status,
                    "redis": redis_status,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            ),
            200,
        )

    # Global Hata Yakalama (500 Internal Server Error)
    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Internal Server Error: %s", error)
        # Kritik bir 500 hatasında alarm tetikle
        from backend.utils.alarms import send_security_alert_task

        send_security_alert_task.delay(
            "Sunucu İç Hatası (500)",
            {
                "username": "Sistem",
                "ip_address": request.remote_addr if request else "N/A",
            },
            f"Beklenmeyen sunucu hatası: {error}",
            severity="CRITICAL",
        )
        return (
            jsonify(
                {
                    "error": "Sunucu hatası, geliştirici bilgilendirildi. Lütfen daha sonra tekrar deneyin."
                }
            ),
            500,
        )

    # HTTP 404 Hata Yakalama
    @app.errorhandler(404)
    def not_found_error(error):
        logger.warning(f"404 Not Found: Yol: {request.path}, IP: {request.remote_addr}")
        return jsonify({"error": "Kaynak bulunamadı."}), 404

    # HTTP 403 Hata Yakalama
    @app.errorhandler(403)
    def forbidden_error(error):
        logger.warning(
            f"403 Forbidden: Yol: {request.path}, IP: {request.remote_addr}, Hata: {error.description}"
        )
        return jsonify({"error": "Erişim engellendi."}), 403

    # SocketIO olayları
    @socketio.on("connect", namespace="/")
    def handle_connect():
        logger.info("Client connected to WebSocket.")
        emit("my response", {"data": "Connected"})

    @socketio.on("connect", namespace="/alerts")
    @check_usage_limit("realtime_alert")
    def handle_alerts_connect(auth):
        api_key = auth.get("api_key") if auth else None
        user = User.query.filter_by(api_key=api_key).first()
        if not user or user.subscription_level.value < SubscriptionPlan.PREMIUM.value:
            logger.warning("Unauthorized alert WebSocket connection attempt.")
            return False
        g.user = user
        logger.info(f"Alerts WebSocket connected: {user.username}")

    @socketio.on("disconnect", namespace="/")
    def handle_disconnect():
        logger.info("Client disconnected from WebSocket.")

    @socketio.on("disconnect", namespace="/alerts")
    def handle_alerts_disconnect():
        logger.info("Client disconnected from alerts WebSocket.")

    return app
