from flask import request
from backend.db import db
from backend.db.models import AuditLog
import os

import requests
import smtplib
from email.mime.text import MIMEText

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
ADMIN_ALERT_EMAIL = os.getenv("ADMIN_ALERT_EMAIL")

# Aksiyon listesi kritik olaylari belirtir
CRITICAL_ACTIONS = [
    "admin_user_deleted",
    "admin_user_banned",
    "admin_login",
    "critical_error",
]


def log_action(user=None, action: str = "", details=None) -> None:
    """Record an audit log entry for the given user action."""
    log = AuditLog(
        user_id=getattr(user, "id", None),
        username=getattr(user, "email", None) or getattr(user, "username", None),
        action=action,
        ip_address=request.remote_addr if request else None,
        details=details,
    )
    db.session.add(log)
    db.session.commit()

    # OTOMATIK UYARI SISTEMI
    if action in CRITICAL_ACTIONS:
        msg = (
            f"[ALERT] {action} by {log.username} from {log.ip_address} at "
            f"{log.created_at}\nDetails: {details}"
        )

        if SLACK_WEBHOOK_URL:
            try:
                requests.post(SLACK_WEBHOOK_URL, json={"text": msg}, timeout=3)
            except Exception:
                pass

        if ADMIN_ALERT_EMAIL:
            try:
                mail = MIMEText(msg)
                mail["Subject"] = f"ALERT: {action}"
                mail["From"] = "noreply@ytdcrypto.com"
                mail["To"] = ADMIN_ALERT_EMAIL
                with smtplib.SMTP(os.getenv("MAIL_SERVER", "localhost"), int(os.getenv("MAIL_PORT", 25))) as server:
                    if os.getenv("MAIL_USE_TLS", "false").lower() == "true":
                        server.starttls()
                    username = os.getenv("MAIL_USERNAME")
                    password = os.getenv("MAIL_PASSWORD")
                    if username and password:
                        server.login(username, password)
                    server.send_message(mail)
            except Exception:
                pass
