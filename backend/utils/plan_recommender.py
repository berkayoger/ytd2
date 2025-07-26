from backend.models.plan import Plan


def recommend_plan(user, usage_stats):
    """Suggest a plan name based on usage stats."""
    plans = Plan.query.filter_by(is_active=True).all()
    for plan in sorted(plans, key=lambda p: p.price):
        features = plan.features_dict()
        max_pred = features.get("max_prediction_per_day", 10)
        if usage_stats.get("predictions", 0) <= max_pred:
            return plan.name
    return "Free"
