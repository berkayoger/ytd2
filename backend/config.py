import os
from datetime import timedelta

class BaseConfig:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///ytd_crypto.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    }
    CELERY_TIMEZONE = "Europe/Istanbul"
    CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
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
    }
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET", "change_me_access")
    REFRESH_TOKEN_SECRET = os.getenv("REFRESH_TOKEN_SECRET", "change_me_refresh")
    ACCESS_TOKEN_EXP_MINUTES = int(os.getenv("ACCESS_TOKEN_EXP_MINUTES", "15"))
    REFRESH_TOKEN_EXP_DAYS = int(os.getenv("REFRESH_TOKEN_EXP_DAYS", "7"))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DEV_DATABASE_URL", "sqlite:///ytd_crypto.db"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )
    CELERY_TASK_ALWAYS_EAGER = True


class ProductionConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///ytd_crypto.db")

