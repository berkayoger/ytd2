# backend/payment/routes.py

from flask import Blueprint, request, jsonify, current_app, g
from loguru import logger
import uuid # conversationId için
from datetime import datetime, timedelta
import json # JSON işlemleri için
from iyzipay import Options, Request
from iyzipay.models import Buyer, Address, BasketItem, Payment, CheckoutFormInitialize
from iyzipay.constant import IyzipayConstants

# Modelleri import et
from backend.db.models import (
    db,
    User,
    SubscriptionPlan,
    PromoCode,
    PromoCodeUsage,
    PaymentTransactionLog,
)
# Güvenlik dekoratörünü import et
from backend.utils.decorators import require_subscription_plan
# Yardımcı fonksiyonları import et
from backend.utils.helpers import add_audit_log
from backend.utils.security import verify_iyzico_signature, check_iyzico_signature
from backend import limiter

payment_bp = Blueprint('payment', __name__)

# Limiter instance from application factory

# Ödeme Başlatma Endpoint'i (Frontend'den çağrılır)
@payment_bp.route('/initiate', methods=['POST'])
@require_subscription_plan(SubscriptionPlan.TRIAL) # Ödeme başlatmak için en az TRIAL planı gereklidir
def initiate_payment():
    user = g.user # Dekorator'den gelen kullanıcı objesi
    data = request.get_json()
    plan_str = data.get("plan")
    # price = data.get("price") # Frontend'den gelen fiyat artık kullanılmıyor
    promo_code_str = data.get("promo_code")

    try:
        if not plan_str:
            return jsonify({"error": "Plan bilgisi eksik."}), 400
    
        # KRİTİK GÜVENLİK KONTROLÜ: Frontend'den gelen planı backend'de doğrula ve fiyatı güvenli kaynaktan çek
        with current_app.app_context():
            # Planın geçerli bir abonelik planı olup olmadığını kontrol et
            try:
                selected_plan = SubscriptionPlan[plan_str.upper()]
            except KeyError:
                add_audit_log(
                    action_type="PAYMENT_INIT_INVALID_PLAN_KEY",
                    actor_id=user.id, actor_username=user.username,
                    target_username=plan_str, details={"ip_address": request.remote_addr},
                    ip_address=request.remote_addr, commit=True
                )
                return jsonify({"error": "Geçersiz abonelik planı."}), 400
            
            # Planın fiyatını backend'deki güvenli kaynaktan çek (hardcode yerine AdminSettings'ten gelmeli)
            # BACKEND_PLAN_PRICES sabitinden çekiyoruz, bu AdminSettings'ten gelmeliydi.
            final_price = current_app.config['BACKEND_PLAN_PRICES'].get(selected_plan.name)
            if final_price is None:
                logger.error(f"Plan {selected_plan.name} için backend'de fiyat tanımlı değil.")
                add_audit_log(
                    action_type="PAYMENT_INIT_MISSING_PRICE_CONFIG",
                    actor_id=user.id, actor_username=user.username,
                    target_username=selected_plan.name, details={"ip_address": request.remote_addr},
                    ip_address=request.remote_addr, commit=True
                )
                return jsonify({"error": "Seçilen plan için fiyat bilgisi bulunamadı."}), 500
    
            # Promosyon Kodu Uygulama (Opsiyonel) - Fiyatı etkileyebilir
            promo_code_obj = None
            if promo_code_str:
                promo_code_obj = PromoCode.query.filter_by(code=promo_code_str, is_active=True).first()
                if promo_code_obj and promo_code_obj.plan.value == selected_plan.value:
                    # Burada promosyon kodunun indirimi düşülebilir veya farklı bir fiyatlandırma modeli uygulanabilir
                    # Örneğin, promo kodu direk paketin kendisini ücretsiz/indirimli yapıyorsa, final_price güncellenmeli.
                    # Şu anki mantıkta, promosyon kodu sadece update_subscription'da planı değiştiriyor.
                    # Ödeme başlatmada promosyon kodunun fiyatı nasıl etkilediği iş kuralına bağlıdır.
                    # Basitlik için, iyzico'ya gönderilen fiyatı (final_price) promo koddan bağımsız tutuyoruz
                    # ancak gerçek entegrasyonda promo kodun fiyatı düşürmesi gerekiyorsa burada final_price güncellenmeli.
                    logger.info(f"Promosyon kodu '{promo_code_str}' ödeme başlatma aşamasında kullanılıyor.")
                    add_audit_log(
                        action_type="PAYMENT_INIT_PROMO_CODE_PRESENT",
                        actor_id=user.id, actor_username=user.username,
                        target_id=promo_code_obj.id, target_username=promo_code_obj.code,
                        details={"plan": selected_plan.name, "initial_price": final_price, "ip_address": request.remote_addr},
                        ip_address=request.remote_addr, commit=False
                    )
                else:
                    logger.warning(f"Kullanıcı {user.username} tarafından geçersiz/aktif olmayan promosyon kodu denemesi: {promo_code_str} (ödeme başlatma)")
                    add_audit_log(
                        action_type="PAYMENT_INIT_INVALID_PROMO_CODE",
                        actor_id=user.id, actor_username=user.username,
                        target_id=None, target_username=promo_code_str,
                        details={"reason": "Invalid or expired promo code during payment init", "ip_address": request.remote_addr},
                        ip_address=request.remote_addr, commit=False
                    )
                    # Promosyon kodu geçersizse ödeme başlatmayı durdur.
                    db.session.commit()
                    return jsonify({"error": "Geçersiz veya aktif olmayan promosyon kodu."}), 400
    
    
            # iyzico API Konfigürasyonu
            options = Options()
            options.api_key = current_app.config['IYZICO_API_KEY']
            options.secret_key = current_app.config['IYZICO_SECRET']
            options.base_url = current_app.config['IYZICO_BASE_URL']
            
            # Ödeme başlatma isteği
            request_iyzico = CheckoutFormInitialize()
            request_iyzico.locale = Request.LOCALE_TR
            request_iyzico.conversation_id = str(uuid.uuid4()) # Benzersiz işlem ID'si
            request_iyzico.price = str(final_price) # iyzico'ya gönderilen fiyat (backend'den doğrulanmış)
            request_iyzico.paid_price = str(final_price) # Kullanıcının ödeyeceği fiyat
            request_iyzico.currency = Payment.CURRENCY_USD # Para birimi (USD olarak ayarlı, iyzico'ya göre ayarla)
    
            # callbackUrl, iyzico'dan ödeme tamamlandığında geri dönecek endpoint
            # Production'da bu URL HTTPS olmalı ve doğru domaini göstermelidir.
            # request.url_root -> 'http://localhost:5000/' döner
            # http -> https dönüşümü production için önemlidir.
            callback_base_url = request.url_root
            if current_app.config['ENV'].lower() == "production":
                 callback_base_url = callback_base_url.replace('http://', 'https://')
            request_iyzico.callback_url = f"{callback_base_url.rstrip('/')}/api/payment/callback"
            
            request_iyzico.basket_id = f"YTD-PLAN-{selected_plan.name}-{user.id}-{request_iyzico.conversation_id}" # Sepet ID'si
            request_iyzico.payment_group = IyzipayConstants.PAYMENT_GROUP_SUBSCRIPTION # Abonelik ödemesi
    
            # Alıcı bilgileri (Oturumdaki kullanıcıdan çekilmeli)
            buyer = Buyer()
            buyer.id = str(user.id)
            buyer.name = user.username # Gerçek ad soyad veritabanında tutulabilir
            buyer.surname = user.username
            buyer.gsm_number = "+905555555555" # Placeholder, gerçek veriden alınmalı
            buyer.email = user.email
            buyer.identity_number = "11111111111" # Placeholder, gerçek veriden alınmalı (TCKN vb.)
            buyer.last_login_date = user.created_at.strftime("%Y-%m-%d %H:%M:%S") # Son login
            buyer.registration_date = user.created_at.strftime("%Y-%m-%d %H:%M:%S") # Kayıt tarihi
            buyer.registration_address = "Adres yok" # Placeholder
            buyer.ip = request.remote_addr
            buyer.city = "Istanbul" # Placeholder
            buyer.country = "Turkey" # Placeholder
            buyer.zip_code = "34000" # Placeholder
            request_iyzico.buyer = buyer
    
            # Adres bilgileri (Alıcı bilgileriyle aynı olabilir, gerçek veriden çekilmeli)
            address = Address()
            address.contact_name = user.username # Veya tam ad soyad
            address.city = "Istanbul"
            address.country = "Turkey"
            address.address = "Adres yok"
            address.zip_code = "34000"
            request_iyzico.shipping_address = address
            request_iyzico.billing_address = address
    
            # Sepet Detayları
            basket_item = BasketItem()
            basket_item.id = f"plan-{selected_plan.name.lower()}"
            basket_item.name = f"YTDCrypto {selected_plan.name.capitalize()} Aboneliği"
            basket_item.category1 = "Yazılım Aboneliği"
            basket_item.item_type = BasketItem.ITEM_TYPE_VIRTUAL # Dijital ürün
            basket_item.price = str(final_price)
            request_iyzico.basket_items = [basket_item]
            
            # iyzico API çağrısı
            checkout_form_initialize = CheckoutFormInitialize.create(request_iyzico, options)
            raw = checkout_form_initialize.to_pki_string()
            iyzico_result = json.loads(raw)
            
            if iyzico_result.get("status") == "success":
                logger.info(f"iyzico ödeme başlatma başarılı. ConversationID: {request_iyzico.conversation_id}, Kullanıcı: {user.username}")
                add_audit_log(
                    action_type="PAYMENT_INITIATED_SUCCESS",
                    actor_id=user.id, actor_username=user.username,
                    target_id=user.id, target_username=user.username,
                    details={
                        "plan": selected_plan.name, 
                        "price": final_price, 
                        "promo_code": promo_code_str,
                        "iyzico_conversation_id": request_iyzico.conversation_id,
                        "iyzico_payment_id": iyzico_result.get("paymentId"),
                        "ip_address": request.remote_addr
                    },
                    ip_address=request.remote_addr, commit=True
                )
                return jsonify({
                    "status": "success",
                    "payment_page_url": iyzico_result.get("paymentPageUrl"),
                    "token": iyzico_result.get("token") # Gerekliyse token'ı da döndür
                })
            else:
                error_message = iyzico_result.get("errorMessage", "Bilinmeyen iyzico hatası.")
                error_code = iyzico_result.get("errorCode", "N/A")
                logger.error(f"iyzico ödeme başlatma hatası. Konuşma ID: {request_iyzico.conversation_id}, Hata: {error_message}, Kod: {error_code}. Kullanıcı: {user.username}")
                add_audit_log(
                    action_type="PAYMENT_INITIATED_FAILED",
                    actor_id=user.id, actor_username=user.username,
                    target_id=user.id, target_username=user.username,
                    details={
                        "plan": selected_plan.name, 
                        "price": final_price, 
                        "promo_code": promo_code_str,
                        "iyzico_error_message": error_message,
                        "iyzico_error_code": error_code,
                        "ip_address": request.remote_addr
                    },
                    ip_address=request.remote_addr, commit=True
                )
                return jsonify({
                    "status": "error",
                    "error": error_message
                }), 400
    
# Ödeme Geri Bildirim (Callback) Endpoint'i (iyzico tarafından çağrılır)
    except Exception as e:
        logger.exception(f"initiate_payment error: {e}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500

@payment_bp.route('/callback', methods=['POST'])
@limiter.limit("60/hour")
def iyzico_callback():
    # KRİTİK GÜVENLİK: iyzico callback'inin doğrulanması hayati önem taşır.
    # Ödeme sağlayıcısının imza doğrulama mekanizmasını kullanmalısınız.
    # Aksi takdirde, sahte callback'lerle abonelikler yükseltilebilir!

    # iyzico genellikle form-urlencoded data gönderir
    sig_error = check_iyzico_signature(current_app.config['IYZICO_SECRET'])
    if sig_error:
        logger.warning("iyzico callback: İmza doğrulaması başarısız.")
        return sig_error

    data = request.form.to_dict()
    
    # iyzico'dan gelen token ve conversationId
    iyzico_token = data.get('token')
    conversation_id = data.get('conversationId')

    if not iyzico_token or not conversation_id:
        logger.error(f"iyzico callback: Token veya conversationId eksik. Data: {data}")
        add_audit_log(
            action_type="PAYMENT_CALLBACK_FAILED_MISSING_DATA",
            actor_username="iyzico_callback_system",
            details={"reason": "Missing token or conversationId", "data": data, "ip_address": request.remote_addr},
            ip_address=request.remote_addr, commit=True
        )
        return "ERROR", 400
    
    # iyzico API Konfigürasyonu
    options = Options()
    options.api_key = current_app.config['IYZICO_API_KEY']
    options.secret_key = current_app.config['IYZICO_SECRET']
    options.base_url = current_app.config['IYZICO_BASE_URL']

    # Ödeme detaylarını iyzico'dan sorgula (Callback'i doğrulamak için en güvenli yol)
    try:
        from iyzipay.models import CheckoutForm
        from iyzipay.request import RetrieveCheckoutFormRequest

        retrieve_request = RetrieveCheckoutFormRequest()
        retrieve_request.locale = Request.LOCALE_TR
        retrieve_request.conversation_id = conversation_id
        retrieve_request.token = iyzico_token

        checkout_form = CheckoutForm.retrieve(retrieve_request, options)
        iyzico_details = json.loads(checkout_form.to_pki_string())

        if iyzico_details.get("status") == "success" and iyzico_details.get("paymentStatus") == "SUCCESS":
            # Ödeme başarılı!
            payment_id = iyzico_details.get("paymentId")
            # 3) Replay saldırı önleme
            if PaymentTransactionLog.query.filter_by(iyzico_payment_id=payment_id, status="SUCCESS").first():
                logger.info(f"Tekrar eden ödeme: {payment_id}, atlandı.")
                return "OK", 200

            total_paid_price = float(iyzico_details.get("paidPrice"))
            basket_id = iyzico_details.get("basketId")
            
            # basket_id'den kullanıcı ID'sini ve planı çıkar
            # Format: YTD-PLAN-{plan_name}-{user_id}-{conversation_id}
            parts = basket_id.split('-')
            if len(parts) < 5 or parts[0] != "YTD" or parts[1] != "PLAN":
                logger.error(f"iyzico callback: Geçersiz basketId formatı: {basket_id}")
                add_audit_log(
                    action_type="PAYMENT_CALLBACK_FAILED_INVALID_BASKET_ID",
                    actor_username="iyzico_callback_system",
                    details={"basket_id": basket_id, "data": iyzico_details, "ip_address": request.remote_addr},
                    ip_address=request.remote_addr, commit=True
                )
                return "ERROR: Invalid basketId", 400

            plan_name_from_basket = parts[2].upper()
            user_id_from_basket = int(parts[3])

            with current_app.app_context(): # DB işlemleri için app context
                user = User.query.get(user_id_from_basket)
                if not user:
                    logger.error(f"iyzico callback: Kullanıcı bulunamadı. User ID: {user_id_from_basket}")
                    add_audit_log(
                        action_type="PAYMENT_CALLBACK_FAILED_USER_NOT_FOUND",
                        actor_username="iyzico_callback_system",
                        target_id=user_id_from_basket, details={"data": iyzico_details, "ip_address": request.remote_addr},
                        ip_address=request.remote_addr, commit=True
                    )
                    return "ERROR: User not found", 404
                
                try:
                    selected_plan = SubscriptionPlan[plan_name_from_basket]
                except KeyError:
                    logger.error(f"iyzico callback: Geçersiz plan adı. Plan: {plan_name_from_basket}")
                    add_audit_log(
                        action_type="PAYMENT_CALLBACK_FAILED_INVALID_PLAN_NAME",
                        actor_username="iyzico_callback_system",
                        target_id=user.id, target_username=user.username,
                        details={"plan_name": plan_name_from_basket, "data": iyzico_details, "ip_address": request.remote_addr},
                        ip_address=request.remote_addr, commit=True
                    )
                    return "ERROR: Invalid plan name", 400

                # KRİTİK GÜVENLİK: Ödenen fiyatı ve planı tekrar doğrula
                # Bu, INITIATE adımında yapılan kontrolle eşleşmeli
                # Backend'de tanımlı fiyatlarla karşılaştır
                expected_price = current_app.config['BACKEND_PLAN_PRICES'].get(selected_plan.name)

                if not expected_price or abs(total_paid_price - expected_price) > 0.01: # Küsürat farkı için tolerans
                    logger.critical(f"iyzico callback: Fiyat doğrulama hatası! Ödenen: {total_paid_price}, Beklenen: {expected_price}. Kullanıcı: {user.username}")
                    add_audit_log(
                        action_type="PAYMENT_CALLBACK_FAILED_PRICE_MISMATCH",
                        actor_username="iyzico_callback_system",
                        target_id=user.id, target_username=user.username,
                        details={"paid_price": total_paid_price, "expected_price": expected_price, "plan": selected_plan.name, "ip_address": request.remote_addr},
                        ip_address=request.remote_addr, commit=True
                    )
                    return "ERROR: Price mismatch", 400

                existing = PaymentTransactionLog.query.filter_by(
                    iyzico_payment_id=payment_id, status="SUCCESS"
                ).first()
                if existing:
                    logger.warning(
                        f"iyzico callback: Tekrar eden ödeme ID'si. Zaten işlendi: {payment_id}"
                    )
                    add_audit_log(
                        action_type="PAYMENT_CALLBACK_DUPLICATE",
                        actor_username="iyzico_callback_system",
                        target_id=user.id,
                        target_username=user.username,
                        details={"iyzico_payment_id": payment_id, "ip_address": request.remote_addr},
                        ip_address=request.remote_addr,
                        commit=True,
                    )
                    return "OK", 200

                # Aboneliği güncelle
                old_level = user.subscription_level.name
                user.subscription_level = selected_plan
                # Abonelik süresi uzatılırken mantık: Eğer mevcut bitiş tarihi gelecekteyse üzerine ekle, yoksa şimdiden başlat
                if user.subscription_end and user.subscription_end > datetime.utcnow():
                    user.subscription_end += timedelta(days=30) # iyzico varsayılan olarak 30 günlük periyot sağlar.
                else:
                    user.subscription_end = datetime.utcnow() + timedelta(days=30)
                
                # Maksimum abonelik süresi kontrolü (ör: 5 yıl)
                MAX_SUBSCRIPTION_EXTENSION_DAYS = current_app.config.get('MAX_SUBSCRIPTION_EXTENSION_DAYS', 5 * 365)
                max_allowed_end_date = datetime.utcnow() + timedelta(days=MAX_SUBSCRIPTION_EXTENSION_DAYS)
                if user.subscription_end > max_allowed_end_date:
                    user.subscription_end = max_allowed_end_date
                    add_audit_log(
                        action_type="SUBSCRIPTION_EXTENDED_TO_MAX_LIMIT",
                        actor_username="iyzico_callback_system",
                        target_id=user.id, target_username=user.username,
                        details={"iyzico_payment_id": payment_id, "reason": "Max subscription duration reached", "new_end_date": user.subscription_end.isoformat()},
                        ip_address=request.remote_addr, commit=False
                    )

                # Token versiyonunu artırarak eski JWT'leri iptal et
                user.token_version += 1
                
                with db.session.begin():
                    db.session.add(
                        PaymentTransactionLog(
                            iyzico_payment_id=payment_id,
                            user_id=user.id,
                            status="SUCCESS",
                        )
                    )
                logger.info(f"iyzico callback: Ödeme başarılı. Kullanıcı {user.username} planı {selected_plan.name} olarak güncellendi.")
                add_audit_log(
                    action_type="PAYMENT_COMPLETED_SUCCESS",
                    actor_username="iyzico_callback_system",
                    target_id=user.id, target_username=user.username,
                    details={"plan": selected_plan.name, "paid_price": total_paid_price, "payment_id": payment_id, "iyzico_token": iyzico_token, "ip_address": request.remote_addr},
                    ip_address=request.remote_addr, commit=True
                )
                return "OK", 200 # iyzico'ya başarı sinyali

        elif iyzico_details.get("status") == "success" and iyzico_details.get("paymentStatus") == "FAILURE":
            # Ödeme başarısız
            error_message = iyzico_details.get("errorMessage", "Ödeme başarısız.")
            logger.warning(f"iyzico callback: Ödeme başarısız. ConversationID: {conversation_id}, Hata: {error_message}. Data: {iyzico_details}")
            add_audit_log(
                action_type="PAYMENT_COMPLETED_FAILURE",
                actor_username="iyzico_callback_system",
                details={"error_message": error_message, "data": iyzico_details, "ip_address": request.remote_addr},
                ip_address=request.remote_addr, commit=True
            )
            if payment_id := iyzico_details.get("paymentId"):
                with db.session.begin():
                    db.session.add(
                        PaymentTransactionLog(
                            iyzico_payment_id=payment_id,
                            user_id=user_id_from_basket,
                            status="FAILURE",
                        )
                    )
            return "FAILURE", 200 # iyzico'ya başarısızlık sinyali
        else:
            # iyzico'dan bilinmeyen durum veya hata
            logger.error(f"iyzico callback: Bilinmeyen ödeme durumu. ConversationID: {conversation_id}. Data: {iyzico_details}")
            add_audit_log(
                action_type="PAYMENT_COMPLETED_UNKNOWN_STATUS",
                actor_username="iyzico_callback_system",
                details={"data": iyzico_details, "ip_address": request.remote_addr},
                ip_address=request.remote_addr, commit=True
            )
            return "ERROR: Unknown status", 400

    except Exception as e:
        logger.exception(f"iyzico callback işlenirken hata oluştu: {e}. Data: {data}")
        add_audit_log(
            action_type="PAYMENT_CALLBACK_PROCESSING_ERROR",
            actor_username="iyzico_callback_system",
            details={"error": str(e), "data": data, "ip_address": request.remote_addr},
            ip_address=request.remote_addr, commit=True
        )
        db.session.rollback() # Hata durumunda tüm transaction'ı geri al
        return "ERROR: Internal server error", 500
