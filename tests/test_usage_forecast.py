import pytest
from datetime import datetime, timedelta
from backend import create_app, db
from backend.db.models import User, UsageLog, UserRole


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
        user = User(username="usagetest", role=UserRole.USER)
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
            UsageLog(user_id=test_user.id, action="generate_chart", timestamp=now),
            UsageLog(user_id=test_user.id, action="generate_chart", timestamp=now),
            UsageLog(user_id=test_user.id, action="forecast", timestamp=now),
            UsageLog(user_id=test_user.id, action="forecast", timestamp=now),
        ])
        db.session.commit()

        count_today = get_usage_count(test_user, "predict_daily")
        assert count_today == 2

        export_count = get_usage_count(test_user, "export")
        assert export_count == 1

        chart_count = get_usage_count(test_user, "generate_chart")
        assert chart_count == 2

        forecast_count = get_usage_count(test_user, "forecast")
        assert forecast_count == 2

        unknown_count = get_usage_count(test_user, "non_existing")
        assert unknown_count == 0


def test_record_usage_log_insert(test_app, test_user):
    from backend.utils.usage_tracking import record_usage

    with test_app.app_context():
        record_usage(test_user, "predict_daily")
        record_usage(test_user, "predict_daily")
        record_usage(test_user, "export")
        record_usage(test_user, "generate_chart")
        record_usage(test_user, "forecast")
        record_usage(test_user, "forecast")

        logs = UsageLog.query.filter_by(user_id=test_user.id).all()
        assert len(logs) == 6

        daily_logs = [log for log in logs if log.action == "predict_daily"]
        export_logs = [log for log in logs if log.action == "export"]
        chart_logs = [log for log in logs if log.action == "generate_chart"]
        forecast_logs = [log for log in logs if log.action == "forecast"]

        assert len(daily_logs) == 2
        assert len(export_logs) == 1
        assert len(chart_logs) == 1
        assert len(forecast_logs) == 2
