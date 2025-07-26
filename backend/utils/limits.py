import json
from backend.db.models import SubscriptionPlanLimits
from loguru import logger


def get_effective_limits(user):
    """
    Kullanıcının planına göre limitleri döndürür.
    Öncelik: custom_features > subscription plan limits
    """
    if user.custom_features:
        try:
            parsed = json.loads(user.custom_features)
            if isinstance(parsed, dict):
                return parsed
            logger.warning(f"custom_features JSON beklenirken farklı tür: {type(parsed)}")
        except Exception as e:
            logger.error(f"custom_features parse hatası: {e}")

    # Plan limitleri fallback
    return SubscriptionPlanLimits.get_limits(user.subscription_level)


def enforce_limit(user, key: str, usage_count: int) -> bool:
    """
    Kullanıcının belirtilen key için limiti aşıp aşmadığını kontrol eder.

    Args:
        user: User nesnesi (custom_features içerebilir)
        key: limit ismi, örn. "predict_daily"
        usage_count: bugüne kadar kullanılan miktar

    Returns:
        True => kullanıma izin verilir
        False => limit aşılmış
    """
    limits = get_effective_limits(user)
    limit_value = limits.get(key)

    if limit_value is None:
        return True  # Sınırsız limit (veya tanımsız), izin ver

    try:
        return usage_count < int(limit_value)
    except Exception as e:
        logger.error(f"Limit kontrolü sırasında hata: {e}")
        return False  # Beklenmedik bir durumda erişimi engelle
