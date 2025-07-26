# backend/api/__init__.py

from flask import Blueprint

# 'api' adında bir Blueprint oluşturuluyor. 
# Bu, API ile ilgili tüm route'ları (uç noktaları) bir araya toplamamızı sağlar.
api_bp = Blueprint('api', __name__)

# Blueprint'e bağlı route'ları (örneğin routes.py veya views.py dosyasındaki) import ediyoruz ki
# ana uygulama tarafından tanınabilsinler.
# Bu satırın çalışması için aynı dizinde route'ları tanımladığınız bir dosya olmalı.
from backend.api import routes
from backend.api import plan_routes
