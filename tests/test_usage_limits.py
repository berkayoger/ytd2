import pytest
from backend.utils.usage_limits import check_usage_limit
from flask import Flask


def dummy_decorator(key):
    def wrapper(fn):
        return fn
    return wrapper


def test_check_usage_limit_decorator():
    app = Flask(__name__)
    with app.app_context():
        from types import SimpleNamespace
        from flask import g
        g.user = SimpleNamespace(id=1, subscription_level=SimpleNamespace(name="PREMIUM"))

        @check_usage_limit("forecast")
        def test_fn():
            return True

        assert test_fn() is True
