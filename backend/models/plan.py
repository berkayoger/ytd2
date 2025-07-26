import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float
from backend.db import db

class Plan(db.Model):
    __tablename__ = 'plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    price = db.Column(db.Float, nullable=False)
    features = db.Column(db.Text, nullable=True)
    discount_price = db.Column(db.Float, nullable=True)
    discount_start = db.Column(db.DateTime, nullable=True)
    discount_end = db.Column(db.DateTime, nullable=True)
    is_public = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def features_dict(self):
        try:
            return json.loads(self.features) if self.features else {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "discount_price": self.discount_price,
            "discount_start": self.discount_start.isoformat() if self.discount_start else None,
            "discount_end": self.discount_end.isoformat() if self.discount_end else None,
            "features": self.features_dict(),
            "is_public": self.is_public,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }
