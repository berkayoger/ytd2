# backend/utils/alarms.py

import requests
from flask import current_app
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from backend.db import db
from backend.db.models import SecurityAlarmLog, AlarmSeverityEnum

# SLACK_COLORS, enum tanımının dışına taşındı ve enum üyeleriyle eşleştirildi.
SLACK_COLORS = {
    AlarmSeverityEnum.INFO.value:    "#4f46e5",
    AlarmSeverityEnum.WARNING.value: "#fbbf24",
    AlarmSeverityEnum.CRITICAL.value:"#ef4444",
    AlarmSeverityEnum.FATAL.value:   "#b91c1c"
}

def send_alarm(
    alert_type: str,
    severity: AlarmSeverityEnum,
    details: str,
    username: str = None,
    ip_address: str = None,
    user_agent: str = None
):
    """
    Veritabanına bir güvenlik alarmı kaydeder ve yapılandırılmışsa Slack'e bildirim gönderir.
    Slack bildirimi, ana işlemi engellememek için kısa bir zaman aşımı ile "fire-and-forget"
    prensibiyle çalışır.
    """
    try:
        # 1. Veritabanına alarmı kaydet.
        # Olası uzun metinlere karşı 'details' alanı veritabanı için kırpılıyor.
        truncated_details = (details[:2000] + '...') if len(details) > 2000 else details
        alarm_log = SecurityAlarmLog(
            alert_type=alert_type,
            severity=severity,
            details=truncated_details,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(alarm_log)
        db.session.commit()
        logger.info(f"Security alarm logged to DB: {alert_type} ({severity.name})")

    except SQLAlchemyError as e:
        logger.exception(f"Veritabanına alarm kaydedilemedi: {alert_type} - {e}")
        db.session.rollback()
        # Veritabanı hatası kritik olduğu için işlemi burada durdur.
        return
    except Exception as e:
        logger.exception(f"Alarm kaydedilirken beklenmedik bir hata oluştu: {e}")
        db.session.rollback()
        return

    # 2. Slack'e bildirim gönder (Veritabanı işlemi başarılı olduktan sonra).
    webhook = current_app.config.get('SLACK_ALARM_WEBHOOK_URL')
    if not webhook:
        logger.warning("SLACK_ALARM_WEBHOOK_URL tanımlı değil, Slack bildirimi atlanıyor.")
    
    socketio = current_app.extensions.get('socketio')

    # Slack'e gönderilecek payload oluşturuluyor.
    payload = {
        "attachments": [{
            "color": SLACK_COLORS.get(severity.value, "#808080"),
            "pretext": f":warning: *New Security Alarm: {alert_type}* | Severity: *{severity.name}*",
            "fields": [
                # Slack'e orijinal, kırpılmamış detayı gönderiyoruz.
                {"title":"Details", "value":details, "short":False},
                # Sadece değer varsa alanı ekle
                *([{"title":"User","value":username,"short":True}] if username else []),
                *([{"title":"IP Address","value":ip_address,"short":True}] if ip_address else []),
                *([{"title":"User Agent","value":user_agent,"short":False}] if user_agent else [])
            ],
            "footer": "YTDCrypto Alarm System",
            "ts": int(alarm_log.created_at.timestamp())
        }]
    }

    try:
        # Kısa timeout ile Slack'e gönder. Bu işlem ana akışı yavaşlatmaz.
        # Hata durumunda sadece loglanır, veritabanı işlemi etkilenmez.
        response = requests.post(webhook, json=payload, timeout=3)
        response.raise_for_status()
        logger.info(f"Slack alarm sent successfully: {alert_type}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Slack bildirimi gönderilemedi (RequestException): {e}")
    except Exception as e:
        logger.error(f"Slack bildirimi gönderilirken beklenmedik bir hata oluştu: {e}")

    if socketio:
        try:
            socketio.emit(
                'alert',
                {
                    'type': alert_type,
                    'severity': severity.value,
                    'details': details
                },
                namespace='/alerts'
            )
        except Exception as e:
            logger.error(f"WebSocket alert emit failed: {e}")
