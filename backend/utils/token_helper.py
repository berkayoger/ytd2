from itsdangerous import URLSafeTimedSerializer
from flask import current_app


def _get_serializer():
    secret = current_app.config.get("JWT_SECRET_KEY", "default-secret")
    return URLSafeTimedSerializer(secret)


def generate_reset_token(email: str) -> str:
    """Create a time-limited password reset token for given email."""
    serializer = _get_serializer()
    return serializer.dumps(email, salt="pw-reset")


def verify_reset_token(token: str, max_age: int = 900) -> str | None:
    """Validate reset token and return email if valid."""
    serializer = _get_serializer()
    try:
        email = serializer.loads(token, salt="pw-reset", max_age=max_age)
        return email
    except Exception:
        return None
