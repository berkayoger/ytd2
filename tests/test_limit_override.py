import json
from backend.db.models import User, SubscriptionPlan
from backend.utils.limits import enforce_limit


def test_enforce_limit_with_custom_override():
    user = User(username="premium_user", subscription_level=SubscriptionPlan.PREMIUM)
    user.custom_features = json.dumps({"predict_daily": 2})
    assert enforce_limit(user, "predict_daily", usage_count=1)
    assert not enforce_limit(user, "predict_daily", usage_count=2)


def test_enforce_limit_fallback_to_plan(monkeypatch):
    class MockSubscriptionPlanLimits:
        @staticmethod
        def get_limits(plan):
            return {"predict_daily": 5}

    monkeypatch.setattr("backend.utils.limits.SubscriptionPlanLimits", MockSubscriptionPlanLimits)

    user = User(username="basic_user", subscription_level=SubscriptionPlan.BASIC)
    user.custom_features = None
    assert enforce_limit(user, "predict_daily", usage_count=4)
    assert not enforce_limit(user, "predict_daily", usage_count=5)


def test_enforce_limit_malformed_json():
    user = User(username="corrupted", subscription_level=SubscriptionPlan.BASIC)
    user.custom_features = "{invalid_json: true"
    assert enforce_limit(user, "predict_daily", usage_count=0)
