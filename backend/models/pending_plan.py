from datetime import datetime
from backend.db import db

class PendingPlan(db.Model):
    __tablename__ = "pending_plans"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"))
    start_at = db.Column(db.DateTime, nullable=False)
    expire_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="pending_plans", lazy=True)
    plan = db.relationship("Plan", lazy=True)
