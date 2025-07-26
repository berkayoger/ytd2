import factory
from backend import db
from backend.db.models import PromotionCode

class PromotionCodeFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PromotionCode
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "commit"

    code = factory.Sequence(lambda n: f"CODE{n}")
    description = "Test promo"
    promo_type = "discount"
    discount_type = "%"
    discount_amount = 50
    feature = None
    plans = "plan1"
    usage_count = 0
    usage_limit = 5
    active_days = 7
    validity_days = 7
    user_segment = "all"
    custom_users = None
    is_active = True
