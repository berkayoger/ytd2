from datetime import datetime
from backend.db import db

class PlanHistory(db.Model):
    __tablename__ = "plan_history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=False)
    device = db.Column(db.String(128))
    ip = db.Column(db.String(64))
    note = db.Column(db.String(256))
    is_automatic = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="plan_history", lazy=True)
    plan = db.relationship("Plan", lazy=True)
