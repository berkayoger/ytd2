from flask import Blueprint, jsonify
from backend.db.models import TechnicalIndicator
from backend.tasks.strategic_recommender import generate_ta_based_recommendation

bp = Blueprint('ta', __name__)


@bp.route('/api/technical/latest')
def latest_ta():
    latest = TechnicalIndicator.query.order_by(TechnicalIndicator.created_at.desc()).first()
    return jsonify(latest.to_dict() if latest else {}), 200


@bp.route('/insight/<symbol>', methods=['GET'])
def technical_insight(symbol):
    data = generate_ta_based_recommendation(symbol)
    if not data:
        return jsonify({"error": "Veri bulunamadı"}), 404
    return jsonify(data)
