# backend/auth/__init__.py

from flask import Blueprint

# 'auth' adında bir Blueprint oluşturuluyor.
# Bu, kimlik doğrulama ile ilgili tüm route'ları (login, register, logout vb.)
# bir araya toplamamızı sağlar.
auth_bp = Blueprint('auth', __name__)

# Blueprint'e bağlı route'ları (örneğin auth/routes.py dosyasındaki) import ediyoruz.
# Bu satır, auth klasöründeki route tanımlamalarını blueprint'e tanıtır.
