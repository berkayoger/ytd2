import os
from celery import Celery
from kombu import Exchange, Queue

celery_app = Celery(
    "ytdcrypto",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)


def init_celery(app):
    """Bind Celery configuration to the Flask app."""
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone=app.config.get("CELERY_TIMEZONE", "UTC"),
        enable_utc=app.config.get("CELERY_ENABLE_UTC", True),
        beat_schedule=app.config.get("CELERY_BEAT_SCHEDULE", {}),
        task_queues=[
            Queue("default", Exchange("default"), routing_key="default"),
        ],
        **{k: v for k, v in app.config.items() if k.startswith("CELERY_")},
    )

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask


def autodiscover_tasks():
    """Import Celery task modules."""
    import backend.tasks.celery_tasks  # noqa
    import backend.tasks.plan_tasks  # noqa


if os.getenv("FLASK_ENV") != "testing":
    autodiscover_tasks()
