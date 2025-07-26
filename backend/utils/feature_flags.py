from flask import current_app


def feature_flag_enabled(flag_name: str) -> bool:
    """Return True if the given feature flag is enabled in app config."""
    flags = current_app.config.get("FEATURE_FLAGS", {}) if current_app else {}
    return bool(flags.get(flag_name, False))

