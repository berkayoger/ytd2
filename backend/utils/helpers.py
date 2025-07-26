# backend/utils/helpers.py



import os

import json

import re

import fcntl

import random

import string

from datetime import datetime, date

from enum import Enum as PyEnum

from typing import Any, Dict, List, Optional



from flask import request

from loguru import logger

from sqlalchemy.exc import SQLAlchemyError



from backend.db import db

# AuditLog modeli bazı ortamlarda mevcut olmayabilir
try:
    from backend.db.models import AuditLog
except Exception:  # pragma: no cover - test ortamları için
    AuditLog = None



# --- Güvenlik ve Temizleme Yardımcıları ---



def auto_sensitive_fields(model_cls: Any) -> List[str]:

    """

    Bir modelin sütunlarını tarar ve bilinen riskli desenlerle eşleşen

    sütun adlarının bir listesini döndürür.

    """

    risky_patterns = ["password", "secret", "token", "key", "recovery", "code", "pin", "hash"]

    return [

        col.name for col in model_cls.__table__.columns

        if any(pattern in col.name.lower() for pattern in risky_patterns)

    ]



def sanitize_log_string(s: Any) -> Any:

    """

    Log enjeksiyonunu ve temel PII sızıntısını önlemek için bir dizeyi temizler.

    """

    if not isinstance(s, str):

        return s

    # Kontrol karakterlerini (yeni satırlar ve sekmeler dahil) kaldır

    s = re.sub(r'[\r\n\t\x00-\x1F\x7F-\x9F]', '', s)

    # Yazdırılamayan karakterleri '?' ile değiştir

    s = ''.join(c if c.isprintable() else '?' for c in s)

    return s



def sanitize_dict(data: Any) -> Any:

    """Bir sözlük veya liste içindeki dize değerlerini yinelemeli olarak temizler."""

    if isinstance(data, dict):

        return {sanitize_log_string(k) if isinstance(k, str) else k: sanitize_dict(v) for k, v in data.items()}

    elif isinstance(data, list):

        return [sanitize_dict(i) for i in data]

    else:

        return sanitize_log_string(data)



# --- Denetim Kaydı (Audit Log) Yardımcıları ---



def audit_log_fallback_file(log_entry: Dict[str, Any]):

    """

    Veritabanı yazma işlemi başarısız olursa, bir log girişini yerel bir dosyaya yazar.

    Dosya kilitleme ve güvenlik kontrolleri kullanarak çoklu işlem güvenliği sağlar.

    """

    fallback_dir = os.getenv("AUDIT_FALLBACK_LOG_DIR", "/var/log/ytcrypto_audit_logs")

    fallback_file = os.path.join(fallback_dir, "auditlog-failsafe.log")



    try:

        if not os.path.exists(fallback_dir):

            os.makedirs(fallback_dir, mode=0o700, exist_ok=True)



        # Symlink saldırılarına karşı kontrol

        if os.path.islink(fallback_file):

            logger.critical(f"Denetim kaydı fallback dosyası bir sembolik link: {fallback_file}. Güvenlik nedeniyle yazma işlemi iptal edildi.")

            return



        # Dosya sahibi UID kontrolü

        if os.path.exists(fallback_file):

            if os.stat(fallback_file).st_uid != os.getuid():

                logger.critical(f"Denetim kaydı fallback dosyası sahibi UID uyuşmazlığı! Beklenen: {os.getuid()}, Bulunan: {os.stat(fallback_file).st_uid}. Yazma işlemi iptal edildi.")

                return



        fd = os.open(fallback_file, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)

        with os.fdopen(fd, "a", encoding="utf-8") as f:

            try:

                fcntl.flock(f, fcntl.LOCK_EX)

                f.write(json.dumps(log_entry, default=str) + "\n")

            finally:

                fcntl.flock(f, fcntl.LOCK_UN)

        logger.info(f"Denetim kaydı başarıyla fallback dosyasına yazıldı: {fallback_file}")

    except Exception as ex:

        logger.critical(f"Denetim kaydı fallback dosyasına yazılamadı: {ex}")



def add_audit_log(

    action_type: str,

    actor_id: Optional[int] = None,

    actor_username: Optional[str] = None,

    target_id: Optional[int] = None,

    target_username: Optional[str] = None,

    details: Optional[Dict[str, Any]] = None,

    ip_address: Optional[str] = None,

    commit: bool = True

) -> None:

    """Sistemdeki önemli eylemleri denetim amacıyla kaydeder."""

    sanitized_details = sanitize_dict(details)

    sanitized_ip = sanitize_log_string(ip_address or request.remote_addr)



    try:

        if AuditLog is None:
            raise RuntimeError("AuditLog model not available")
        log_entry = AuditLog(

            action_type=action_type,

            actor_id=actor_id,

            actor_username=sanitize_log_string(actor_username),

            target_id=target_id,

            target_username=sanitize_log_string(target_username),

            details=json.dumps(sanitized_details, default=str) if sanitized_details else None,

            ip_address=sanitized_ip

        )

        db.session.add(log_entry)

        if commit:

            db.session.commit()

    except Exception as e:

        db.session.rollback()

        logger.error(f"Denetim günlüğü kaydedilemedi, fallback deneniyor: {e}")

        log_data_for_fallback = {

            "action_type": action_type, "actor_username": actor_username,

            "details": sanitized_details, "ip_address": sanitized_ip,

            "timestamp": datetime.utcnow().isoformat(), "error": str(e)

        }

        audit_log_fallback_file(log_data_for_fallback)



# --- Veri Serileştirme ve Maskeleme ---



def serialize_model(obj: Any, exclude_fields: Optional[List[str]] = None) -> Dict[str, Any]:

    """

    Bir SQLAlchemy model nesnesini, hassas alanları hariç tutarak bir sözlüğe dönüştürür.

    """

    if not obj:

        return {}

       

    model_sensitive_fields = getattr(obj.__class__, '__sensitive_fields__', [])

    all_excluded = set(auto_sensitive_fields(obj.__class__) + model_sensitive_fields + (exclude_fields or []))



    out = {}

    for col in obj.__table__.columns:

        if col.name in all_excluded:

            continue

        val = getattr(obj, col.name)

        if isinstance(val, (datetime, date)):

            out[col.name] = val.isoformat()

        elif isinstance(val, PyEnum):

            out[col.name] = val.name

        else:

            out[col.name] = val

    return out



def mask_email(email: str) -> str:

    """Bir e-posta adresini güvenli bir şekilde maskeler."""

    if not email or '@' not in email:

        return email

    name, domain = email.split('@', 1)

    return name[0] + '****' + '@' + domain


def is_user_accessible(user: Any) -> bool:
    """RBAC için temel kullanıcı erişilebilirlik kontrolü."""
    return not getattr(user, 'is_locked', False)


def serialize_user_for_api(user: Any, scope: str = 'public') -> Dict[str, Any]:
    """Kullanıcı nesnesini güvenli şekilde sözlüğe çevirir."""
    if not user:
        return {}

    data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'subscription_level': user.subscription_level.name if getattr(user, 'subscription_level', None) else None,
        'subscription_start': user.subscription_start.isoformat() if getattr(user, 'subscription_start', None) else None,
        'subscription_end': user.subscription_end.isoformat() if getattr(user, 'subscription_end', None) else None,
        'is_active': user.is_subscription_active() if hasattr(user, 'is_subscription_active') else False,
    }
    if scope == 'self':
        data.update({
            'api_key': user.api_key,
            'is_locked': getattr(user, 'is_locked', False),
            'locked_until': user.locked_until.isoformat() if getattr(user, 'locked_until', None) else None,
        })
    return data



# --- Diğer Yardımcı Fonksiyonlar ---



def bulk_insert_records(records: list, chunk_size: int = 1000):

    """

    Veritabanına toplu olarak kayıt ekler. Büyük listeleri parçalara böler.

    """

    if not records:

        return

    try:

        with db.session.begin():

            for i in range(0, len(records), chunk_size):

                db.session.bulk_save_objects(records[i:i + chunk_size])

        logger.info(f"{len(records)} adet kayıt başarıyla eklendi.")

    except Exception as e:

        logger.exception(f"Toplu kayıt ekleme sırasında hata: {e}")

        db.session.rollback()



def generate_random_code(length: int = 6, alphanumeric: bool = False) -> str:

    """İsteğe bağlı olarak alfanümerik, güvenli bir rastgele kod üretir."""

    chars = string.digits

    if alphanumeric:

        chars += string.ascii_uppercase

    return ''.join(random.choices(chars, k=length))
