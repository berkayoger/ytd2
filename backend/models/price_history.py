from datetime import datetime
from backend.db import db

class PriceHistory(db.Model):
    __tablename__ = "price_history"
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=False)
    old_price = db.Column(db.Float)
    new_price = db.Column(db.Float)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    changed_by = db.Column(db.String(64))

    plan = db.relationship("Plan", lazy=True)
