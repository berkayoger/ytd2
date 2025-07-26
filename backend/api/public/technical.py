from flask import Blueprint, jsonify
from backend.db.models import TechnicalIndicator
from sqlalchemy import desc

technical_bp = Blueprint("technical", __name__, url_prefix="/api/technical")

@technical_bp.route("/latest", methods=["GET"])
def get_latest_technical():
    record = TechnicalIndicator.query.order_by(desc(TechnicalIndicator.created_at)).first()
    if not record:
        return jsonify({})

    return jsonify({
        "symbol": record.symbol,
        "rsi": round(record.rsi, 2) if record.rsi is not None else None,
        "macd": round(record.macd, 2) if record.macd is not None else None,
        "signal": round(record.signal, 2) if record.signal is not None else None,
        "created_at": record.created_at.isoformat()
    })
