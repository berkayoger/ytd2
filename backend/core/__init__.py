from flask import Blueprint

# 'core' adında bir Blueprint oluşturuluyor.
# Bu, uygulamanın ana arayüz sayfaları (index, about vs.) gibi
# temel rotalarını gruplamak için kullanılır.
core_bp = Blueprint('core', __name__, template_folder='templates')

# Bu Blueprint'e bağlı route'ları (örneğin core/routes.py dosyasındaki) import ediyoruz.
from backend.core import routes
