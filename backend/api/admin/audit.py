from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.db import db
from backend.db.models import AuditLog

audit_bp = Blueprint("audit_bp", __name__)


# LOG LİSTELEME (FİLTRE DESTEKLİ)
@audit_bp.route("/admin/audit-logs", methods=["GET"])
@jwt_required()
@admin_required()
def get_logs():
    limit = int(request.args.get("limit", 100))
    username = request.args.get("username")
    action = request.args.get("action")
    ip = request.args.get("ip")

    q = AuditLog.query
    if username:
        q = q.filter(AuditLog.username.ilike(f"%{username}%"))
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if ip:
        q = q.filter(AuditLog.ip_address == ip)

    logs = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return jsonify([
        {
            "id": l.id,
            "user_id": l.user_id,
            "username": l.username,
            "action": l.action,
            "ip_address": l.ip_address,
            "details": l.details,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ])

# LOG RETENTION (ESKİ KAYITLARI SİL)
@audit_bp.route("/admin/audit-logs/purge", methods=["DELETE"])
@jwt_required()
@admin_required()
def purge_old_logs():
    from datetime import datetime, timedelta

    days = int(request.args.get("days", 90))
    threshold = datetime.utcnow() - timedelta(days=days)
    deleted = AuditLog.query.filter(AuditLog.created_at < threshold).delete()
    db.session.commit()
    return jsonify({"deleted": deleted})
