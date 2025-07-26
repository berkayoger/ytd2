# backend/constants.py

import os
from datetime import timedelta

# ── Environment Variable Keys ──────────────────────────────────────────────────

IYZICO_API_KEY_ENV                  = "IYZICO_API_KEY"
IYZICO_SECRET_ENV                   = "IYZICO_SECRET"
IYZICO_BASE_URL_ENV                 = "IYZICO_BASE_URL"

SLACK_ALARM_WEBHOOK_ENV             = "SLACK_ALARM_WEBHOOK_URL"

CELERY_BROKER_URL_ENV               = "CELERY_BROKER_URL"
CELERY_RESULT_BACKEND_ENV           = "CELERY_RESULT_BACKEND"

AUDIT_FALLBACK_LOG_DIR_ENV          = "AUDIT_FALLBACK_LOG_DIR"
AUDIT_FALLBACK_FILE_SIZE_LIMIT_ENV  = "AUDIT_FALLBACK_FILE_SIZE_LIMIT_MB"

# ── Iyzico Callback / Payment ─────────────────────────────────────────────────

IYZICO_SIGNATURE_HEADER            = "X-Iyzico-Signature"
IYZICO_SIGNATURE_HEADER_LOWER      = "x-iyzico-signature"
IYZICO_CALLBACK_RATE_LIMIT         = "60/hour"

PRICE_MISMATCH_TOLERANCE           = 0.01  # USD

BASKET_ID_PREFIX                   = "YTD-PLAN"
CALLBACK_URL_PATH                  = "/api/payment/callback"

# ── Subscription & Usage Limits ───────────────────────────────────────────────

TRIAL_DURATION_DAYS                = 7
SUBSCRIPTION_EXTENSION_DAYS        = 30
MAX_SUBSCRIPTION_EXTENSION_DAYS    = 5 * 365  # 5 yıl

# BASIC planı için:
BASIC_WEEKLY_VIEW_LIMIT            = 10
BASIC_ALLOWED_COINS                = [
    "bitcoin",
    "ethereum",
    "ripple",
    "litecoin",
    "cardano",
]

# ── API ve Harici Servis Ayarları ──────────────────────────────────────────────

API_TIMEOUT_SECONDS                = 15  # saniye

# ── Yatırımcı Profilleri ─────────────────────────────────────────────────────

DEFAULT_INVESTOR_PROFILE           = "moderate"
SUPPORTED_INVESTOR_PROFILES        = ["aggressive", "moderate", "conservative"]

# ── Güvenlik & Yetkilendirme ───────────────────────────────────────────────────

PASSWORD_RESET_TOKEN_EXPIRES_MINUTES = 60  # dakika
TWO_FACTOR_CODE_EXPIRES_SECONDS      = 300  # saniye (5 dakika)
ACCOUNT_LOCK_DURATION_MINUTES        = 15   # başarısız girişten sonra kilit süresi

# ── Audit‐Log Fallback ─────────────────────────────────────────────────────────

AUDIT_FALLBACK_LOG_DIR             = os.getenv(
    AUDIT_FALLBACK_LOG_DIR_ENV,
    "/var/log/ytcrypto_audit_logs"
)
AUDIT_FALLBACK_FILE_NAME           = "auditlog-failsafe.log"
AUDIT_FALLBACK_FILE_SIZE_LIMIT_MB  = int(os.getenv(
    AUDIT_FALLBACK_FILE_SIZE_LIMIT_ENV,
    50
))

# ── Celery Queues ─────────────────────────────────────────────────────────────

CELERY_DEFAULT_QUEUE               = "default"
CELERY_ANALYSIS_QUEUE              = "analysis"
