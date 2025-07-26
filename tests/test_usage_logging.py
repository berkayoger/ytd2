import pytest
from datetime import datetime, timedelta
from backend import create_app, db
from backend.db.models import User, UsageLog, UserRole, SubscriptionPlan


@pytest.fixture
def test_app(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    app = create_app()
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def test_user(test_app):
    with test_app.app_context():
        # create a basic plan with prediction limits so enforce_plan_limit passes
        from backend.models.plan import Plan
        import json
        plan = Plan(name="basic", price=0.0, features=json.dumps({"prediction": 5, "predict_daily": 5}))
        db.session.add(plan)
        db.session.commit()

        user = User(username="usagetest", role=UserRole.USER, plan_id=plan.id, subscription_level=SubscriptionPlan.BASIC)
        user.set_password("pass")
        user.generate_api_key()
        db.session.add(user)
        db.session.commit()
        return user


def test_get_usage_count(test_app, test_user):
    from backend.utils.usage_limits import get_usage_count

    with test_app.app_context():
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        db.session.add_all([
            UsageLog(user_id=test_user.id, action="predict_daily", timestamp=now),
            UsageLog(user_id=test_user.id, action="predict_daily", timestamp=now),
            UsageLog(user_id=test_user.id, action="predict_daily", timestamp=yesterday),
            UsageLog(user_id=test_user.id, action="export", timestamp=now),
            UsageLog(user_id=test_user.id, action="download", timestamp=now),
            UsageLog(user_id=test_user.id, action="download", timestamp=yesterday),
        ])
        db.session.commit()

        count_today = get_usage_count(test_user, "predict_daily")
        assert count_today == 2

        export_count = get_usage_count(test_user, "export")
        assert export_count == 1

        download_count = get_usage_count(test_user, "download")
        assert download_count == 1

        unknown_count = get_usage_count(test_user, "non_existing")
        assert unknown_count == 0


def test_record_usage_log_insert(test_app, test_user):
    from backend.utils.usage_tracking import record_usage

    with test_app.app_context():
        record_usage(test_user, "predict_daily")
        record_usage(test_user, "predict_daily")
        record_usage(test_user, "export")
        record_usage(test_user, "download")

        logs = UsageLog.query.filter_by(user_id=test_user.id).all()
        assert len(logs) == 4

        daily_logs = [log for log in logs if log.action == "predict_daily"]
        export_logs = [log for log in logs if log.action == "export"]
        download_logs = [log for log in logs if log.action == "download"]

        assert len(daily_logs) == 2
        assert len(export_logs) == 1
        assert len(download_logs) == 1


def test_predict_usage_log(test_app, test_user):
    from backend import db
    from backend.db.models import UsageLog

    with test_app.test_client() as client:
        with test_app.app_context():
            token = test_user.generate_access_token()
            db.session.commit()

            headers = {
                "X-API-KEY": test_user.api_key,
                "Content-Type": "application/json"
            }
            data = {"coin": "BTC"}
            response = client.post("/api/predict/", json=data, headers=headers)
            assert response.status_code == 200

            logs = UsageLog.query.filter_by(user_id=test_user.id, action="predict_daily").all()
            assert len(logs) == 1
