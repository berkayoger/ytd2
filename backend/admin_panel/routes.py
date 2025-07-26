# backend/admin_panel/routes.py

from flask import jsonify, request, current_app
from . import admin_bp
from backend.db.models import (
    db,
    User,
    ABHData,
    DBHData,
    AdminSettings,
    PromoCode,
    SubscriptionPlan,
    UserRole,
    SubscriptionPlanModel,
)
from sqlalchemy import func, text
from loguru import logger
import os
import uuid
from datetime import datetime, timedelta
import json
from backend.utils.rbac import require_permission
from backend.auth.middlewares import admin_required as _admin_required
from flask_jwt_extended import get_jwt_identity
from backend.utils.audit import log_action


def admin_required(f):
    return _admin_required()(f)

# Kullanıcı Yönetimi
# Tüm kullanıcıları listeleme endpoint'i
@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    with current_app.app_context():
        users = User.query.all()
        user_list = [
            {
                "id": user.id,
                "username": user.username,
                "subscription_level": user.subscription_level.value,
                "role": user.role.value,
                "api_key": user.api_key, # Üretimde doğrudan API key'i döndürmeyin!
                "is_active_subscriber": user.is_subscription_active(),
                "subscription_end": user.subscription_end.isoformat() if user.subscription_end else None,
                "created_at": user.created_at.isoformat(),
                "custom_features": user.custom_features or "{}",
            }
            for user in users
        ]
        return jsonify(user_list), 200


@admin_bp.route('/users/<int:user_id>/custom-features', methods=['GET'])
@admin_required
def get_custom_features(user_id):
    """Belirli bir kullanıcının özel özelliklerini döndürür."""
    with current_app.app_context():
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Kullanıcı bulunamadı"}), 404

        try:
            custom_data = (
                json.loads(user.custom_features)
                if isinstance(user.custom_features, str)
                else user.custom_features or {}
            )
            db.session.commit()
            return jsonify({"custom_features": custom_data}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500


@admin_bp.route('/users/<int:user_id>/custom-features', methods=['POST'])
@admin_required
def update_custom_features(user_id):
    data = request.get_json()
    if not data or "custom_features" not in data:
        return jsonify({"error": "Eksik veri"}), 400

    try:
        parsed = json.loads(data["custom_features"])
    except json.JSONDecodeError:
        return jsonify({"error": "Geçersiz JSON"}), 400

    with current_app.app_context():
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Kullanıcı bulunamadı"}), 404

        user.custom_features = json.dumps(parsed)
        db.session.commit()

    return jsonify({"message": "Özel özellikler güncellendi."}), 200

# Kullanıcı detaylarını ve abonelik/rol güncelleme
@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user_details(user_id):
    data = request.get_json()
    new_level_str = data.get('subscription_level')
    new_role_str = data.get('role')

    with current_app.app_context():
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Kullanıcı bulunamadı."}), 404
        
        if new_level_str:
            try:
                selected_plan = SubscriptionPlan[new_level_str.upper()]
                user.subscription_level = selected_plan
                # Plan güncellendiğinde abonelik başlangıç/bitiş tarihlerini de yönetebilirsiniz
                # Ödeme entegrasyonu yoksa, manuel olarak bir süre belirleyebilirsiniz.
                if selected_plan not in [SubscriptionPlan.TRIAL, SubscriptionPlan.BASIC]: # Trial ve Basic için süre uzatılmaz
                     user.subscription_start = datetime.utcnow()
                     user.subscription_end = datetime.utcnow() + timedelta(days=30) # Örn: 30 günlük standart
                elif selected_plan == SubscriptionPlan.TRIAL:
                    user.subscription_start = datetime.utcnow() # Deneme yeniden başlar gibi
                    user.subscription_end = datetime.utcnow() + timedelta(days=7) # Yeni deneme süresi
                # Eğer Basic'e çekilirse subscription_end'i null yapabiliriz veya mevcut süreyi koruyabiliriz.
                # user.subscription_end = None # Eğer Basic'e çekiliyorsa süresiz yapma
            except KeyError:
                return jsonify({"error": "Geçersiz abonelik seviyesi."}), 400
        
        if new_role_str:
            try:
                user.role = UserRole[new_role_str.upper()]
            except KeyError:
                return jsonify({"error": "Geçersiz kullanıcı rolü."}), 400

        db.session.commit()
        logger.info(f"Kullanıcı {user.username} detayları güncellendi.")
        admin_id = get_jwt_identity()
        admin_user = User.query.get(admin_id) if admin_id else None
        log_action(
            admin_user,
            action="plan_update",
            details=f"Kullanıcı {user.username}, yeni plan: {user.subscription_level.value}",
        )
        return jsonify({"message": "Kullanıcı başarıyla güncellendi.", "user": {
            "id": user.id,
            "username": user.username,
            "subscription_level": user.subscription_level.value,
            "role": user.role.value,
            "is_active_subscriber": user.is_subscription_active(),
            "subscription_end": user.subscription_end.isoformat() if user.subscription_end else None
        }}), 200

# İçerik ve Konfigürasyon Yönetimi

# Yeni coin ekleme endpoint'i (şimdilik basit bir simülasyon)
@admin_bp.route('/coins', methods=['POST'])
@admin_required
def add_coin():
    data = request.get_json()
    coin_id = data.get('id')
    coin_name = data.get('name')
    coin_symbol = data.get('symbol')

    if not all([coin_id, coin_name, coin_symbol]):
        return jsonify({"error": "Coin ID, ad ve sembol gerekli."}), 400
    
    # Gerçek implementasyonda, burada yeni coini veritabanına kaydedebilir (yeni bir Coin modeli olabilir),
    # ve backend'in veri toplama sürecini bu yeni coin için başlatabilirsiniz.
    logger.info(f"Yeni coin ekleme talebi: {coin_name} ({coin_id})")
    return jsonify({"message": f"Coin '{coin_name}' başarıyla eklendi (Simüle edildi)."})

# Web sitesi arka planını alma/güncelleme
@admin_bp.route('/website_settings/background', methods=['GET', 'POST'])
@admin_required
def manage_website_background():
    with current_app.app_context():
        if request.method == 'GET':
            setting = AdminSettings.query.filter_by(setting_key='homepage_background_url').first()
            url = setting.setting_value if setting else "https://www.coinkolik.com/wp-content/uploads/2023/12/gunun-one-cikan-kripto-paralari-30-aralik-2023.jpg" # Varsayılan URL
            return jsonify({"homepage_background_url": url}), 200
        elif request.method == 'POST':
            data = request.get_json()
            new_url = data.get('url')
            if not new_url:
                return jsonify({"error": "URL eksik."}), 400
            
            setting = AdminSettings.query.filter_by(setting_key='homepage_background_url').first()
            if setting:
                setting.setting_value = new_url
            else:
                setting = AdminSettings(setting_key='homepage_background_url', setting_value=new_url)
                db.session.add(setting)
            db.session.commit()
            logger.info(f"Anasayfa arka planı güncellendi: {new_url}")
            return jsonify({"message": "Arka plan başarıyla güncellendi.", "new_url": new_url}), 200

# Abonelik fiyatlarını ve özelliklerini yönetme (GET ve POST)
@admin_bp.route('/subscription_plans', methods=['GET', 'POST'])
@admin_required
def manage_subscription_plans():
    with current_app.app_context():
        if request.method == 'GET':
            plans_config = {}
            for plan_enum in SubscriptionPlan:
                # Trial planı için statik veya dinamik değerler
                if plan_enum == SubscriptionPlan.TRIAL:
                    plans_config[plan_enum.value] = {
                        "price": "0.00",
                        "features": ["7 Gün Ücretsiz Deneme", "Temel Analiz Raporları", "Popüler Coinlere Erişim"],
                        "limits": {"analyze_calls_per_day": 5, "llm_queries_per_day": 2} # Örnek limitler
                    }
                    continue

                setting = AdminSettings.query.filter_by(setting_key=f'plan_config_{plan_enum.value}').first()
                if setting:
                    plans_config[plan_enum.value] = json.loads(setting.setting_value)
                else: # Varsayılan değerler
                    plans_config[plan_enum.value] = {
                        "price": "9.99" if plan_enum == SubscriptionPlan.BASIC else "14.99" if plan_enum == SubscriptionPlan.ADVANCED else "19.99",
                        "features": [f"{plan_enum.value.capitalize()} Plan Özelliği 1", f"{plan_enum.value.capitalize()} Plan Özelliği 2"],
                        "limits": {"analyze_calls_per_day": 10 if plan_enum == SubscriptionPlan.BASIC else 50 if plan_enum == SubscriptionPlan.ADVANCED else 9999,
                                   "llm_queries_per_day": 5 if plan_enum == SubscriptionPlan.BASIC else 20 if plan_enum == SubscriptionPlan.ADVANCED else 9999}
                    }
            return jsonify(plans_config), 200

        elif request.method == 'POST':
            data = request.get_json()
            plan_id = data.get('plan_id') # "basic", "advanced", "premium"
            price = data.get('price')
            features = data.get('features') # Liste
            limits = data.get('limits') # Dictionary (örn: {"analyze_calls_per_day": 10})

            if not all([plan_id, price, features, limits]):
                return jsonify({"error": "Plan ID, fiyat, özellikler ve limitler eksik."}), 400
            
            if plan_id.upper() not in SubscriptionPlan._member_map_:
                return jsonify({"error": "Geçersiz plan ID."}), 400
            
            if SubscriptionPlan[plan_id.upper()] == SubscriptionPlan.TRIAL:
                return jsonify({"error": "Deneme planı doğrudan düzenlenemez."}), 400 # Trial'ı admin değiştirmez

            plan_config_value = json.dumps({
                "price": str(price),
                "features": features,
                "limits": limits
            })

            setting = AdminSettings.query.filter_by(setting_key=f'plan_config_{plan_id}').first()
            if setting:
                setting.setting_value = plan_config_value
            else:
                setting = AdminSettings(setting_key=f'plan_config_{plan_id}', setting_value=plan_config_value)
                db.session.add(setting)
            db.session.commit()
            logger.info(f"Abonelik planı {plan_id} güncellendi.")
            return jsonify({"message": f"Plan {plan_id} başarıyla güncellendi."}), 200

# Abonelik kodları yönetimi
@admin_bp.route('/promo_codes', methods=['GET'])
@admin_required
def list_promo_codes():
    with current_app.app_context():
        codes = PromoCode.query.all()
        code_list = [
            {
                "id": code.id,
                "code": code.code,
                "plan": code.plan.value,
                "duration_days": code.duration_days,
                "max_uses": code.max_uses,
                "current_uses": code.current_uses,
                "is_active": code.is_active,
                "expires_at": code.expires_at.isoformat() if code.expires_at else None,
                "created_at": code.created_at.isoformat()
            } for code in codes
        ]
        return jsonify(code_list), 200

@admin_bp.route('/promo_codes', methods=['POST'])
@admin_required
def generate_promo_code():
    data = request.get_json()
    plan_str = data.get('plan')
    duration_days = data.get('duration_days') # Kodun sağladığı abonelik süresi (gün olarak)
    max_uses = data.get('max_uses', 1) 
    expires_at_str = data.get('expires_at') # Opsiyonel: Kodun bitiş tarihi

    if not all([plan_str, duration_days]):
        return jsonify({"error": "Plan ve süre bilgisi eksik."}), 400
    
    try:
        plan_enum = SubscriptionPlan[plan_str.upper()]
        code_value = str(uuid.uuid4())[:8].upper() # Basit bir kod
        
        expires_at = None
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str) # ISO formatından datetime'a çevir
        else: # Eğer son kullanma tarihi belirtilmezse, süresi duration_days'e göre hesapla
            expires_at = datetime.utcnow() + timedelta(days=duration_days) 

        with current_app.app_context():
            new_code = PromoCode(
                code=code_value,
                plan=plan_enum,
                duration_days=duration_days,
                max_uses=max_uses,
                expires_at=expires_at
            )
            db.session.add(new_code)
            db.session.commit()
            logger.info(f"Yeni promosyon kodu üretildi: {code_value} for plan {plan_str}.")
            return jsonify({"message": "Promosyon kodu başarıyla üretildi.", "code": code_value, "plan": plan_str, "duration_days": duration_days, "max_uses": max_uses, "expires_at": expires_at.isoformat()}), 201
    except KeyError:
        return jsonify({"error": "Geçersiz plan adı."}), 400
    except Exception as e:
        logger.error(f"Promosyon kodu üretme hatası: {e}")
        return jsonify({"error": f"Promosyon kodu üretilirken hata oluştu: {str(e)}"}), 500

# Promosyon kodunu kullanma endpoint'i (Kullanıcı tarafı API'de de olabilir)
@admin_bp.route('/promo_codes/apply', methods=['POST'])
def apply_promo_code():
    api_key = request.headers.get('X-API-KEY') # Kullanıcının API anahtarı
    data = request.get_json()
    promo_code = data.get('code')

    if not all([api_key, promo_code]):
        return jsonify({"error": "API anahtarı ve promosyon kodu gerekli."}), 400
    
    with current_app.app_context():
        user = User.query.filter_by(api_key=api_key).first()
        if not user:
            return jsonify({"error": "Geçersiz API anahtarı."}), 401
        
        code = PromoCode.query.filter_by(code=promo_code, is_active=True).first()

        if not code:
            return jsonify({"error": "Geçersiz veya aktif olmayan promosyon kodu."}), 400
        
        if code.expires_at and datetime.utcnow() > code.expires_at:
            code.is_active = False # Süresi dolmuşsa pasif yap
            db.session.commit()
            return jsonify({"error": "Promosyon kodunun süresi dolmuş."}), 400

        if code.current_uses >= code.max_uses:
            code.is_active = False # Kullanım limiti dolmuşsa pasif yap
            db.session.commit()
            return jsonify({"error": "Promosyon kodunun kullanım limiti dolmuş."}), 400
        
        # Kodu uygula: Kullanıcının abonelik seviyesini ve bitiş tarihini güncelle
        user.subscription_level = code.plan
        user.subscription_start = datetime.utcnow()
        user.subscription_end = datetime.utcnow() + timedelta(days=code.duration_days)
        code.current_uses += 1 # Kullanım sayısını artır

        # Eğer kodun tüm kullanımları bittiyse veya tek kullanımlıksa pasif yap
        if code.current_uses >= code.max_uses:
            code.is_active = False
        
        db.session.commit()
        logger.info(f"Promosyon kodu '{promo_code}' kullanıcı {user.username} için uygulandı. Yeni plan: {user.subscription_level.value}.")
        return jsonify({"message": f"Promosyon kodu başarıyla uygulandı. Yeni planınız: {user.subscription_level.value.upper()}.", "new_plan": user.subscription_level.value}), 200


# ── Abonelik Planları CRUD ─────────────────────────────────────────────

@admin_bp.route('/plans', methods=['GET', 'POST'])
@admin_required
def plans():
    with current_app.app_context():
        if request.method == 'GET':
            plans = SubscriptionPlanModel.query.all()
            return jsonify([
                {
                    "id": p.id,
                    "name": p.name,
                    "duration": p.duration_days,
                    "price": p.price,
                    "description": p.description,
                    "active": p.is_active,
                }
                for p in plans
            ]), 200

        data = request.get_json() or {}
        name = data.get("name")
        duration = data.get("duration")
        price = data.get("price")
        description = data.get("description", "")
        is_active = bool(data.get("active", True))
        if not all([name, duration, price]):
            return jsonify({"error": "Plan adı, süre ve fiyat gerekli."}), 400
        if SubscriptionPlanModel.query.filter_by(name=name).first():
            return jsonify({"error": "Bu isimde bir plan zaten var."}), 400
        plan = SubscriptionPlanModel(
            name=name,
            duration_days=int(duration),
            price=float(price),
            description=description,
            is_active=is_active,
        )
        db.session.add(plan)
        db.session.commit()
        return jsonify({"id": plan.id}), 201


@admin_bp.route('/plans/<int:plan_id>', methods=['PATCH', 'DELETE'])
@admin_required
def plan_detail(plan_id):
    with current_app.app_context():
        plan = SubscriptionPlanModel.query.get_or_404(plan_id)
        if request.method == 'PATCH':
            data = request.get_json() or {}
            if "name" in data:
                if plan.name != data["name"] and SubscriptionPlanModel.query.filter_by(name=data["name"]).first():
                    return jsonify({"error": "Bu isimde bir plan zaten var."}), 400
                if plan.name.upper() in ["TRIAL", "BASIC", "PREMIUM"]:
                    return jsonify({"error": "Bu plan değiştirilemez."}), 403
                plan.name = data["name"]
            if "duration" in data:
                plan.duration_days = int(data["duration"])
            if "price" in data:
                plan.price = float(data["price"])
            if "description" in data:
                plan.description = data["description"]
            if "is_active" in data or "active" in data:
                plan.is_active = bool(data.get("is_active", data.get("active")))
            db.session.commit()
            return jsonify({"message": "Plan güncellendi."}), 200

        # DELETE
        if plan.name.upper() in ["TRIAL", "BASIC", "PREMIUM"]:
            return jsonify({"error": "Bu plan silinemez."}), 403
        db.session.delete(plan)
        db.session.commit()
        return jsonify({"message": "Plan silindi."}), 200


@admin_bp.route('/plans/usage', methods=['GET'])
@admin_required
def plan_usage():
    with current_app.app_context():
        counts = (
            db.session.query(User.subscription_level, func.count(User.id))
            .group_by(User.subscription_level)
            .all()
        )
        return (
            jsonify([
                {"plan": plan.name, "user_count": count} for plan, count in counts
            ]),
            200,
        )


@admin_bp.route('/limit-usage', methods=['GET'])
@admin_required
def limit_usage():
    with current_app.app_context():
        results = db.session.execute(
            text(
                """
                SELECT usage_log.user_id, users.username, usage_log.action, COUNT(*) AS count
                FROM usage_log
                JOIN users ON usage_log.user_id = users.id
                GROUP BY usage_log.user_id, users.username, usage_log.action
                ORDER BY count DESC
                LIMIT 100
                """
            )
        )
        stats = [dict(row) for row in results]
        return jsonify({"stats": stats}), 200


