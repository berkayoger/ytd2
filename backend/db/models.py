from datetime import datetime, timedelta

# SQLAlchemy instance uygulama genelinde 'backend.db' paketinde tanımlıdır.
# Bazı ortamlarda 'backend.db.__init__' şeklinde içe aktarmak yeni bir modül
# oluşturabildiğinden, tekil nesnenin kullanılması için doğrudan paket
# üzerinden içe aktarma yapılır.
from backend.db import db
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from enum import Enum
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import (
    Table,
    Column,
    Integer,
    ForeignKey,
    String,
    Float,
    Text,
    DateTime,
    Date,
    Boolean,
)


# --- Enums ---


class SubscriptionPlan(Enum):
    """Abonelik Planı Enum'u - Integer değerler atanarak sıralama garantisi sağlandı"""

    TRIAL = 0
    BASIC = 1
    ADVANCED = 2
    PREMIUM = 3


class SubscriptionPlanLimits:
    """Provides plan based limit configurations."""

    @staticmethod
    def get_limits(plan: SubscriptionPlan) -> dict:
        from backend.utils.plan_limits import PLAN_LIMITS
        return PLAN_LIMITS.get(plan.name.lower(), {})


class UserRole(Enum):
    """Kullanıcı Rolü Enum'u (Yönetici Paneli için)"""

    USER = "user"
    ADMIN = "admin"
    FINANCE_ADMIN = "finance_admin"
    CONTENT_ADMIN = "content_admin"
    SYSTEM_ADMIN = "system_admin"


class AlarmSeverityEnum(Enum):
    """Alarm Şiddeti Enum'u"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"

    SLACK_COLORS = {
        "info": "#4f46e5",
        "warning": "#fbbf24",
        "critical": "#ef4444",
        "fatal": "#b91c1c",
    }


class CeleryTaskStatus(Enum):
    """Celery Görev Durumları"""

    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"


# --- Many-to-Many Association Table for RBAC ---

role_permissions = Table(
    "role_permissions",
    db.Model.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)

# --- Core Models ---


class Role(db.Model):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    permissions = db.relationship(
        "Permission", secondary=role_permissions, backref="roles", lazy=True
    )


class Permission(db.Model):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), nullable=True)


class User(db.Model):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=True, index=True)
    password_hash = Column(String(128), nullable=False)
    api_key = Column(String(128), unique=True, nullable=False, index=True)
    subscription_level = Column(
        SqlEnum(SubscriptionPlan, name="subscription_plan_enum", create_type=True),
        default=SubscriptionPlan.TRIAL,
        nullable=False,
    )
    subscription_start = Column(DateTime, default=datetime.utcnow, nullable=False)
    subscription_end = Column(DateTime, nullable=True)
    role = Column(
        SqlEnum(UserRole, name="user_role_enum", create_type=True),
        default=UserRole.USER,
        nullable=False,
    )
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    role_obj = db.relationship("Role", backref="users", foreign_keys=[role_id])
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    plan = db.relationship("Plan", backref="users")
    plan_expire_at = Column(DateTime, nullable=True)
    boost_features = Column(Text, nullable=True)
    boost_expire_at = Column(DateTime, nullable=True)
    custom_features = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_key(self):
        self.api_key = str(uuid.uuid4())
        return self.api_key

    def generate_access_token(self):
        """Return a short-lived JWT access token for this user."""
        from backend.auth.jwt_utils import generate_tokens

        access, _refresh, _csrf = generate_tokens(
            self.id,
            self.username,
            self.role.value if isinstance(self.role, Enum) else self.role,
        )
        return access

    def is_subscription_active(self):
        if self.subscription_level in [
            SubscriptionPlan.BASIC,
            SubscriptionPlan.ADVANCED,
            SubscriptionPlan.PREMIUM,
        ]:
            if self.subscription_end is None:
                return True
            return datetime.utcnow() < self.subscription_end
        elif self.subscription_level == SubscriptionPlan.TRIAL:
            trial_duration = timedelta(days=7)
            return datetime.utcnow() < (self.created_at + trial_duration)
        return False

    def get_usage_count(self, key):
        """Return usage count for the given feature key."""
        from backend.db.models import UsageLog

        if key == "prediction":
            return UsageLog.query.filter_by(user_id=self.id, action="prediction").count()
        elif key == "download":
            return UsageLog.query.filter_by(user_id=self.id, action="download").count()
        return UsageLog.query.filter_by(user_id=self.id, action=key).count()

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.name if self.role else None,
            "subscription_level": self.subscription_level.name
            if self.subscription_level
            else None,
            "is_active": self.is_active,
            "plan": self.plan.to_dict() if self.plan else None,
            "plan_expire_at": self.plan_expire_at.isoformat() if self.plan_expire_at else None,
            "boost_features": self.boost_features,
            "boost_expire_at": self.boost_expire_at.isoformat() if self.boost_expire_at else None,
            "custom_features": self.custom_features,
        }


# --- Data Warehouse Models ---


class ABHData(db.Model):
    """Analiz Bilgi Havuzu: Dış kaynaklardan toplanan ham veriler."""

    __tablename__ = "abh_data"
    id = Column(Integer, primary_key=True)
    source = Column(Text)
    type = Column(Text)
    content = Column(Text)
    timestamp = Column(Text, index=True)
    coin = Column(Text, index=True)
    tags = Column(Text)


class DBHData(db.Model):
    """Değerlendirilmiş Bilgi Havuzu: İşlenmiş, zenginleştirilmiş analiz sonuçları."""

    __tablename__ = "dbh_data"
    id = Column(Integer, primary_key=True)
    coin = Column(Text, index=True)
    timestamp = Column(Text, index=True)

    # Geliştirilmiş Teknik Analiz Alanları
    rsi = Column(Float)
    macd = Column(Float)
    bb_upper = Column(Float)
    bb_lower = Column(Float)
    stochastic_oscillator = Column(Float)
    candlestick_pattern = Column(String(100))  # e.g., 'Engulfing Bullish'

    # Geliştirilmiş Duygu Analizi Alanları
    news_sentiment = Column(Float)
    twitter_sentiment = Column(Float)
    social_volume = Column(Integer)

    # Geliştirilmiş On-Chain Veri Alanları
    active_addresses = Column(Integer)
    exchange_inflow = Column(Float)
    exchange_outflow = Column(Float)

    # Geliştirilmiş Tahmin Alanları
    forecast_next_day = Column(Float)
    forecast_upper_bound = Column(Float)  # Güven aralığı üst bandı
    forecast_lower_bound = Column(Float)  # Güven aralığı alt bandı
    forecast_explanation = Column(Text)
    volatility = Column(Float)

    # Karar Motoru Sonuçları ve Risk Yönetimi
    signal = Column(Text)
    confidence = Column(Float)
    risk_level = Column(Text)
    suggested_stop_loss = Column(Float)
    suggested_position_size = Column(Float)


# --- System & Security Models ---


class UserSession(db.Model):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    refresh_token = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    user = db.relationship("User", backref="sessions", lazy=True)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reset_token = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="password_reset_tokens", lazy=True)


class DailyUsage(db.Model):
    """Kullanıcıların günlük API kullanımını takip eder."""

    __tablename__ = "daily_usage"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    analyze_calls = Column(Integer, default=0, nullable=False)
    llm_queries = Column(Integer, default=0, nullable=False)
    user = db.relationship("User", backref="daily_usages", lazy=True)
    __table_args__ = (db.UniqueConstraint("user_id", "date", name="_user_date_uc"),)


class SecurityAlarmLog(db.Model):
    """Güvenlik olaylarını ve alarmları kaydeder."""

    __tablename__ = "security_alarm_logs"
    id = Column(Integer, primary_key=True)
    alert_type = Column(String(100), nullable=False)
    username = Column(String(80), nullable=True, index=True)
    ip_address = Column(String(45), nullable=True, index=True)
    user_agent = Column(String(255), nullable=True)
    severity = Column(
        SqlEnum(AlarmSeverityEnum, name="alarm_severity_enum", create_type=True),
        nullable=False,
        default=AlarmSeverityEnum.INFO,
    )
    details = Column(Text, nullable=True)
    seen_by_admin = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "username": self.username,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "severity": self.severity.name if self.severity else None,
            "details": self.details,
            "seen_by_admin": self.seen_by_admin,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
        }


class BacktestResult(db.Model):
    """Karar motoru kurallarının geriye dönük test sonuçlarını saklar."""

    __tablename__ = "backtest_results"
    id = Column(Integer, primary_key=True)
    coin = Column(String(50), nullable=False)
    profile = Column(String(50), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    profit_pct = Column(Float)
    total_trades = Column(Integer)
    win_rate = Column(Float)
    max_drawdown = Column(Float)
    sharpe_ratio = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class CeleryTaskLog(db.Model):
    """Asenkron Celery görevlerinin durumunu ve sonuçlarını kaydeder."""

    __tablename__ = "celery_task_logs"
    id = Column(Integer, primary_key=True)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    task_name = Column(String(255), nullable=True)
    status = Column(
        SqlEnum(CeleryTaskStatus, name="celery_task_status_enum", create_type=True),
        default=CeleryTaskStatus.PENDING,
    )
    result = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# --- Marketing & Admin Models (Existing) ---


class AdminSettings(db.Model):
    __tablename__ = "admin_settings"
    id = Column(Integer, primary_key=True)
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_value = Column(Text, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PromoCode(db.Model):
    __tablename__ = "promo_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(128), nullable=True)
    plan = Column(
        SqlEnum(SubscriptionPlan, name="promo_code_plan_enum", create_type=True),
        nullable=False,
    )
    duration_days = Column(Integer, nullable=False)
    max_uses = Column(Integer, nullable=False, default=1)
    current_uses = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String(120), nullable=True)
    is_single_use_per_user = Column(Boolean, default=False, nullable=False)
    assigned_user = db.relationship(
        "User",
        backref="assigned_promo_codes",
        foreign_keys=[assigned_user_id],
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "description": self.description,
            "plan": self.plan.name if self.plan else None,
            "duration_days": self.duration_days,
            "max_uses": self.max_uses,
            "current_uses": self.current_uses,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "assigned_user_id": self.assigned_user_id,
            "user_email": self.user_email,
            "is_single_use_per_user": self.is_single_use_per_user,
        }


class PromoCodeUsage(db.Model):
    __tablename__ = "promo_code_usages"
    id = Column(Integer, primary_key=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    promo_code = db.relationship("PromoCode", backref="usages", lazy=True)
    user = db.relationship("User", backref="promo_code_usages", lazy=True)
    __table_args__ = (
        db.UniqueConstraint("promo_code_id", "user_id", name="_promo_user_uc"),
        db.Index("idx_promo_code_id", "promo_code_id"),
    )


class PromotionCode(db.Model):
    """Advanced promotion codes supporting flexible discount rules."""

    __tablename__ = "promotion_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    promo_type = Column(String(50), nullable=True)
    discount_type = Column(String(50), nullable=True)
    discount_amount = Column(Float, nullable=True)
    feature = Column(String(100), nullable=True)
    plans = Column(Text, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    usage_limit = Column(Integer, default=1, nullable=True)
    active_days = Column(Integer, nullable=True)
    validity_days = Column(Integer, nullable=True)
    user_segment = Column(String(50), nullable=True)
    custom_users = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "description": self.description,
            "promoType": self.promo_type,
            "discountType": self.discount_type,
            "discountAmount": self.discount_amount,
            "feature": self.feature,
            "plans": self.plans,
            "usage": self.usage_count,
            "usageLimit": self.usage_limit,
            "activeDays": self.active_days,
            "validityDays": self.validity_days,
            "userSegment": self.user_segment,
            "customUsers": self.custom_users,
            "createdAt": self.created_at.strftime("%Y-%m-%d"),
            "isActive": self.is_active,
        }


class PendingAction(db.Model):
    __tablename__ = "pending_actions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    verification_code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="pending_actions", lazy=True)


class TwoFACode(db.Model):
    __tablename__ = "twofa_codes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    code = Column(String(8), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="twofa_codes", lazy=True)
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "action_type", name="_user_action_type_uc_for_2fa_active_code"
        ),
    )


class DeviceLog(db.Model):
    __tablename__ = "device_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_fingerprint = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=False)
    logged_in_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship("User", backref="device_logs", lazy=True)
    __table_args__ = (
        db.UniqueConstraint("user_id", "device_fingerprint", name="_user_device_uc"),
    )


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(80), nullable=False)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(255), nullable=True)
    success = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaymentTransactionLog(db.Model):
    __tablename__ = "payment_transaction_logs"
    id = Column(Integer, primary_key=True)
    iyzico_payment_id = Column(String(100), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship("User", backref="payment_logs", lazy=True)


class SubscriptionPlanModel(db.Model):
    """Dinamik abonelik planlarını saklar."""

    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    duration_days = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class UsageLimitModel(db.Model):
    __tablename__ = "usage_limits"

    id = Column(Integer, primary_key=True)
    plan_name = Column(String(50), nullable=False)  # e.g., 'BASIC', 'PREMIUM'
    feature = Column(String(100), nullable=False)  # e.g., 'LLM', 'forecast', 'alerts'
    daily_limit = Column(Integer, nullable=True)  # null ise sınırsız
    monthly_limit = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("plan_name", "feature", name="_plan_feature_uc"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "plan_name": self.plan_name,
            "feature": self.feature,
            "daily_limit": self.daily_limit,
            "monthly_limit": self.monthly_limit,
            "created_at": self.created_at.isoformat(),
        }


class PredictionOpportunity(db.Model):
    """Yüksek potansiyelli trade fırsatlarını saklar."""

    __tablename__ = "prediction_opportunities"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    current_price = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    forecast_horizon = Column(String(50), nullable=True)
    expected_gain_pct = Column(Float, nullable=False)
    expected_gain_days = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True, default=0.0)
    trend_type = Column(String(50), nullable=False, default="short_term")
    source_model = Column(String(100), nullable=False, default="AIModel")
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "current_price": self.current_price,
            "target_price": self.target_price,
            "forecast_horizon": self.forecast_horizon,
            "expected_gain_pct": self.expected_gain_pct,
            "expected_gain_days": self.expected_gain_days,
            "description": self.description,
            "confidence_score": self.confidence_score,
            "trend_type": self.trend_type,
            "source_model": self.source_model,
            "is_active": self.is_active,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat(),  # time info
        }


class TechnicalIndicator(db.Model):
    __tablename__ = "technical_indicators"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    rsi = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    signal = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "rsi": self.rsi,
            "macd": self.macd,
            "signal": self.signal,
            "created_at": self.created_at.isoformat(),
        }


class AuditLog(db.Model):
    """Stores user actions for auditing purposes."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(128), nullable=True)
    action = Column(String(128), nullable=False)
    ip_address = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="audit_logs", lazy=True)


class UsageLog(db.Model):
    __tablename__ = "usage_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    action = Column(String(64), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class DatabaseBackup(db.Model):
    """Stores database backup metadata."""

    __tablename__ = "database_backups"

    id = Column(Integer, primary_key=True)
    filename = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_hash = Column(String(64), nullable=False)

    admin = db.relationship("User", lazy=True)


class SystemEvent(db.Model):
    """Stores system events and operational logs."""

    __tablename__ = "system_events"

    id = Column(Integer, primary_key=True)
    event_type = Column(String(32), nullable=False)
    level = Column(String(16), nullable=False)
    message = Column(String(512), nullable=False)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = db.relationship("User", lazy=True)

