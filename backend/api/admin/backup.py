from flask import Blueprint, send_file, request, jsonify, abort
from flask_jwt_extended import jwt_required
from backend.auth.middlewares import admin_required
from backend.db import db
from backend.db.models import DatabaseBackup, User
from backend.utils.audit import log_action
import os
import subprocess
import hashlib
from datetime import datetime

backup_bp = Blueprint("backup", __name__, url_prefix="/api/admin/backup")

BACKUP_DIR = os.path.join(os.getcwd(), "backups")
RETENTION = int(os.getenv("BACKUP_RETENTION", "5"))
DB_FILE = os.getenv("DATABASE_FILE", "ytd_crypto.db")


def ensure_backup_dir():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)


@backup_bp.route("", methods=["POST"])
@jwt_required()
@admin_required()
def create_backup():
    ensure_backup_dir()
    admin_id = request.headers.get("X-Admin-ID")
    admin = User.query.get(admin_id) if admin_id else None

    filename = f"backup_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.db"
    path = os.path.join(BACKUP_DIR, filename)

    # only works for sqlite; in tests we assume sqlite
    subprocess.run(["sqlite3", DB_FILE, f".backup {path}"], check=False)

    with open(path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    entry = DatabaseBackup(filename=filename, admin_id=admin.id if admin else None, file_hash=file_hash)
    db.session.add(entry)
    db.session.commit()
    log_action(admin, "backup_created", filename)

    # retention logic
    backups = DatabaseBackup.query.order_by(DatabaseBackup.created_at.desc()).all()
    if len(backups) > RETENTION:
        for old in backups[RETENTION:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old.filename))
            except FileNotFoundError:
                pass
            db.session.delete(old)
        db.session.commit()

    return jsonify({"ok": True, "id": entry.id, "filename": filename})


@backup_bp.route("/list", methods=["GET"])
@jwt_required()
@admin_required()
def list_backups():
    backups = DatabaseBackup.query.order_by(DatabaseBackup.created_at.desc()).limit(20).all()
    return jsonify([
        {
            "id": b.id,
            "filename": b.filename,
            "created_at": b.created_at.isoformat(),
            "admin_id": b.admin_id,
        }
        for b in backups
    ])


@backup_bp.route("/download/<int:backup_id>", methods=["GET"])
@jwt_required()
@admin_required()
def download_backup(backup_id):
    backup = DatabaseBackup.query.get_or_404(backup_id)
    path = os.path.join(BACKUP_DIR, backup.filename)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True)


@backup_bp.route("/restore", methods=["POST"])
@jwt_required()
@admin_required()
def restore_backup():
    data = request.get_json() or {}
    backup_id = data.get("backup_id")
    if not backup_id:
        return jsonify({"error": "backup_id required"}), 400
    backup = DatabaseBackup.query.get_or_404(backup_id)
    path = os.path.join(BACKUP_DIR, backup.filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404

    admin_id = request.headers.get("X-Admin-ID")
    admin = User.query.get(admin_id) if admin_id else None

    subprocess.run(["cp", path, DB_FILE], check=False)
    log_action(admin, "backup_restored", backup.filename)
    return jsonify({"ok": True})

