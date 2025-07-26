# backend/frontend/__init__.py

from flask import Blueprint

# 'frontend' adında bir Blueprint oluşturuluyor.
# Bu blueprint, React/Vue/Angular gibi bir SPA'nın (Single Page Application)
# build edilmiş statik dosyalarını (index.html, css, js) sunmak için kullanılır.
#
# 'static_folder': Frontend'in build edildiği klasörün yolu. 
#                  Genellikle 'build/static' veya benzeri bir yapıdadır.
# 'template_folder': 'index.html' dosyasının bulunduğu klasör.
#
# Yolların projenizin yapısına göre ayarlanması gerekebilir.
# Örneğin, projenizin kök dizininde bir 'frontend/build' klasörü varsa,
# yollar '../frontend/build/static' gibi göreceli olabilir.
frontend_bp = Blueprint(
    'frontend', 
    __name__,
    template_folder='build',
    static_folder='build/static'
)

# Bu Blueprint'e bağlı route'ları import ediyoruz.
# Genellikle tüm istekleri index.html'e yönlendiren tek bir route olur.
from backend.frontend import routes
