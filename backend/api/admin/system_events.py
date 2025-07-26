from datetime import datetime, timedelta
import json
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.db.models import db, SystemEvent
from backend.utils.system_events import log_event


events_bp = Blueprint("events_bp", __name__, url_prefix="/api/admin")


@events_bp.route("/events", methods=["GET"])
@jwt_required()
@admin_required()
def list_events():
    q = SystemEvent.query
    event_type = request.args.get("event_type")
    level = request.args.get("level")
    user_id = request.args.get("user_id")
    search = request.args.get("search")
    start = request.args.get("start")
    end = request.args.get("end")
    if event_type:
        q = q.filter(SystemEvent.event_type == event_type)
    if level:
        q = q.filter(SystemEvent.level == level)
    if user_id:
        q = q.filter(SystemEvent.user_id == int(user_id))
    if search:
        q = q.filter(SystemEvent.message.ilike(f"%{search}%"))
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
            q = q.filter(SystemEvent.created_at >= start_dt)
        except ValueError:
            pass
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
            q = q.filter(SystemEvent.created_at <= end_dt)
        except ValueError:
            pass
    limit = int(request.args.get("limit", 100))
    events = q.order_by(SystemEvent.created_at.desc()).limit(limit).all()
    return jsonify([
        {
            "id": e.id,
            "event_type": e.event_type,
            "level": e.level,
            "message": e.message,
            "meta": json.loads(e.meta) if e.meta else {},
            "created_at": e.created_at.isoformat(),
            "user_id": e.user_id,
        }
        for e in events
    ])


@events_bp.route("/events/retention-cleanup", methods=["POST"])
@jwt_required()
@admin_required()
def retention_cleanup():
    days = int(request.json.get("days", 30)) if request.is_json else 30
    threshold = datetime.utcnow() - timedelta(days=days)
    deleted = SystemEvent.query.filter(SystemEvent.created_at < threshold).delete()
    db.session.commit()
    admin_id = request.headers.get("X-Admin-ID")
    log_event("retention_cleanup", "INFO", f"{deleted} events removed", {"days": days}, user_id=admin_id)
    return jsonify({"deleted": deleted})


@events_bp.route("/status", methods=["GET"])
@jwt_required()
@admin_required()
def system_status():
    db_status = "online"
    redis_status = "online"
    try:
        db.session.execute("SELECT 1")
    except Exception as e:
        db_status = f"error: {e}"
    try:
        current_app.extensions["redis_client"].ping()
    except Exception as e:
        redis_status = f"error: {e}"
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
    except Exception:
        cpu = mem = None
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    job_count = SystemEvent.query.filter(
        SystemEvent.event_type == "job", SystemEvent.created_at >= one_hour_ago
    ).count()
    return jsonify(
        {
            "database": db_status,
            "redis": redis_status,
            "cpu_percent": cpu,
            "memory_percent": mem,
            "jobs_last_hour": job_count,
        }
    )
