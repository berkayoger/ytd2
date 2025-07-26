# YTD Kripto

Bu proje Flask tabanlı bir kripto para analiz uygulamasıdır. Depo iki ana kısımdan oluşur:

* **backend/** - Flask API ve analiz servisleri
* **frontend/** - Basit HTML arayüzü

Ek olarak `scripts/` dizininde yardımcı araçlar bulunur.

Hızlı bir analiz denemek için `scripts/crypto_ta.py` dosyasını çalıştırabilirsiniz.
Bu betik CoinGecko servisine erişim olmadığında örnek verilerle teknik
analiz göstergelerini hesaplar.

Gerçek zamanlı fiyat bilgisini almak için `backend/utils/price_fetcher.py`
içindeki `fetch_current_price` fonksiyonu kullanılabilir. Ağ sorunu olduğunda
fonksiyon `None` döndürür ve görevler bunu ele alacak şekilde tasarlanmıştır.

Backend klasör yapısı aşağıdaki gibidir:

```
backend/
├── __init__.py           # create_app fonksiyonunu dışa açar
├── api/
│   ├── __init__.py       # API Blueprint tanımı
│   └── routes.py         # Analiz endpointleri
├── auth/
│   ├── __init__.py       # Auth Blueprint'i
│   └── routes.py         # Kullanıcı işlemleri
├── admin_panel/
│   ├── __init__.py       # Admin Blueprint'i
│   └── routes.py         # Yönetici paneli
├── db/
│   ├── __init__.py       # SQLAlchemy db nesnesi
│   └── models.py         # Veritabanı modelleri
├── core/
│   ├── __init__.py       # Boş
│   └── services.py       # YTD servis sınıfları
├── tasks/
│   ├── __init__.py       # Celery paket tanımı
│   └── celery_tasks.py   # Görevler
├── requirements.txt
├── .env.example
└── Dockerfile
```

Ana dizinlerin sorumluluklari:
- **api/**: REST API uc noktalari
- **auth/**: kullanici kaydi, giris ve JWT yonetimi
- **admin_panel/**: yonetici paneli rotalari
- **core/**: analiz servisleri ve is mantigi
- **db/**: SQLAlchemy modelleri
- **tasks/**: Celery gorev tanimlari
- **config.py**: ortam tabanli ayarlar
- **frontend/**: statik HTML ve JavaScript
- **migrations/**: veritabani guncelleme scriptleri
- **tests/**: otomatik testler

## Proje Mimarisi ve Teknoloji Yigini

Bu proje servis odakli bir mimariye sahiptir. Backend katmani Flask uzerinde calisir ve REST API sunar. Celery agir islemleri arka planda yurutur ve zamanlanmis gorevleri yonetir. SQLAlchemy veritabanina erisim saglar, Redis hem onbellek hem de Celery brokeri olarak kullanilir. Docker tum servislerin izole calismasini kolaylastirir. Frontend mevcutta basit bir MPA yapisindadir ancak uzun vadede React benzeri bir framework ile SPA mimarisine gecis hedeflenmektedir. Flask'in sadeligi ve Python ekosistemiyle uyumu hizli prototipleme imkani saglar.


Proje kök dizininde `wsgi.py` adlı bir çalıştırıcı dosya bulunur. Bu dosya
`backend.create_app()` fonksiyonunu kullanarak Flask uygulamasını başlatır.


## Mobil Uyumlu Panel

Admin ve kullanıcı sayfaları mobil cihazlarda da rahat kullanılabilmesi için responsive hâle getirildi. HTML dosyalarına `viewport` meta etiketi eklendi ve tablolar `overflow-x-auto` sınıfı ile yatay kaydırılabilir yapıldı. Böylece küçük ekranlarda menü ve kritik işlemler erişilebilir oldu.

## Kurulum

1. Depoyu klonlayın ve gerekli bağımlılıkları kurun:

```bash
pip install -r backend/requirements.txt
```

Flask-Migrate ile veritabanı şema değişikliklerini yönetmek için ilk kez şu adımları uygulayın:

```bash
flask db init
flask db migrate -m "initial"
flask db upgrade
```

2. `.env.example` dosyasını `.env` olarak kopyalayın ve gerekli API anahtarlarını doldurun.

3. Gerekli konfigürasyon sınıfı `FLASK_ENV` değişkeni ile seçilir. Varsayılan
   değer `development`'tır. Örneğin test ortamı için:

```bash
export FLASK_ENV=testing
```

4. Uygulamayı yerel ortamda çalıştırmak için:

```bash
python wsgi.py
```

## Docker ile Çalıştırma

Docker yüklüyse projeyi şu komutla hızlıca başlatabilirsiniz:

```bash
docker-compose up --build
```

## Production Kurulumu (Gunicorn ve Nginx)

Gerçek bir sunucuda uygulamayı yayınlamak için `app.py` dosyası üzerinden
`create_app` fonksiyonunu kullanarak Gunicorn çalıştırabilirsiniz:

```bash
gunicorn -w 4 -b 127.0.0.1:5000 'app:create_app()'
```

Ardından Nginx'i ters proxy olarak yapılandırıp statik dosyaları servis
edecek şekilde ayarlayabilirsiniz. Örnek bir konfigürasyon:

```nginx
server {
    listen 80;
    server_name admin.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static/ {
        alias /path/to/your/frontend/;
    }
}
```

HTTPS sertifikası için Let's Encrypt (`certbot --nginx`) ve güvenlik için UFW
kuralları eklemeniz önerilir. Uygulamanın arka planda kalıcı olarak
çalışması için Supervisor kullanılabilir.

## Testler

Testleri çalıştırmak için `pytest` kullanılabilir:

```bash
pytest
```
Testler unit, integration ve functional klasorlerine ayrilacak sekilde organize edilir. Kod kalitesi icin `pytest-cov` kullanilarak kapsama raporu alinabilir:

```bash
pytest --cov=backend --cov=frontend tests/
```

## API Dokumantasyonu

Backend API'lari OpenAPI (Swagger) standardina uygun sekilde belgelenmektedir. Calisan bir sunucu uzerinde `/api/docs` adresinden interaktif dokumanlara erisilebilir. Bu yontem frontend gelistiricileri icin net bir kontrat saglar ve API surumlerini takip etmeyi kolaylastirir.

### Analytics Uc Noktalari

Yonetim panelindeki gelismis raporlar icin eklenen API'lar:

- `/api/admin/analytics/summary` – Belirli tarihler arasinda aktif kullanici, yeni kayit, odeme ve pasif kullanici sayilarini dondurur.
- `/api/admin/analytics/plans` – Abonelik planlarina gore kullanici dagilimini listeler.
- `/api/admin/analytics/usage` – Yapilan toplam tahmin ve sistem olayi sayisini dondurur.

## Guvenlik Notlari

Sifreler `werkzeug` kutuphanesi ile guclu bicimde hashlenir ve JWT tabanli oturumlar kullanilir. Kullanici girislerinde olusan **refresh token** degeri `user_sessions` tablosunda saklanir ve token yenileme islemlerinde bu tablo uzerinden dogrulama yapilir. CSRF korumasi icin her istek `X-CSRF-Token` basligi ile dogrulanir. RBAC modeli ile yetki kontrolu saglanir. Flask-Limiter kullanilarak API istekleri oran sinirlariyla korunur. Hassas islemler Celery uzerinden gerceklestirilir ve kritik olaylarda `send_security_alert_task` tetiklenerek loglama yapilir.

## Dosya Açıklamaları

Bu bölümde proje deposundaki ana dosya ve klasörlerin kısa açıklamaları listelenmiştir. Uygulamanın yapısı hakkında hızlı bir bakış sağlar.

### Kök Dizin

- `wsgi.py` - Flask uygulamasını başlatan giriş noktası.
- `.env.example` ve `.env` - Ortam değişkenlerini tanımlayan örnek dosyalar.
- `.github/` - CI iş akışlarının yer aldığı klasör.
- `docker-compose.yml` - Gerekli servisleri içeren Docker bileşen tanımı.
- `scripts/` - Kurulum ve geliştirmeye yardımcı betikler.
- `backend/` - Sunucu tarafı uygulama kodları.
- `frontend/` - Statik HTML dosyaları ve istemci betikleri.
- `migrations/` - Veritabanı göç dosyaları.
- `tests/` - Pytest birim testleri.

### `backend/` Klasörü

- `__init__.py` - `create_app` fonksiyonunu içerir, uygulamayı ve uzantıları yapılandırır.
- `config.py` - Ortama özel yapılandırma sınıfları.
- `constants.py` - Abonelik planı ile ilgili sabit değerler.
- `Dockerfile` - API servisinin Docker imajı için talimatlar.
- `requirements.txt` - Backend bağımlılık listesi.
- `.env.example` - Backend için örnek ortam değişkenleri.

Alt klasörler:

* `api/`
  * `__init__.py` - API Blueprint tanımı.
  * `routes.py` - Kripto para analiz uç noktaları.
* `auth/`
  * `__init__.py` - Kimlik doğrulama Blueprint'i.
  * `jwt_utils.py` - JWT üretme ve doğrulama yardımcıları.
  * `middlewares.py` - JWT ve CSRF kontrolü yapan dekoratörler.
  * `routes.py` - Kullanıcı kayıt/giriş işlemleri.
* `admin_panel/`
  * `__init__.py` - Yönetici paneli Blueprint'i.
  * `routes.py` - Yöneticiye özel API uç noktaları.
* `db/`
  * `__init__.py` - SQLAlchemy `db` nesnesi.
  * `models.py` - Kullanıcı, oturum ve abonelik tabloları gibi veritabanı modelleri.
* `core/`
  * `__init__.py` - Boş modül dosyası.
  * `services.py` - Analiz ve tahmin işlemlerini yöneten sınıflar.
* `tasks/`
  * `__init__.py` - Celery paket tanımı.
  * `celery_tasks.py` - Arka plan görevleri ve zamanlanmış işler.
* `frontend/`
  * `__init__.py` - Basit Blueprint.
  * `routes.py` - HTML şablonlarını sunan rotalar.
* `payment/`
  * `routes.py` - Ödeme işlemleri için API uç noktaları.
* `templates/` - Sunucu taraflı render edilen Jinja2 şablonları.
* `utils/`
  * `alarms.py` - Slack/Telegram gibi yerlere uyarı gönderen yardımcılar.
  * `decorators.py` - Abonelik planı ve izin kontrolleri için dekoratörler.
  * `helpers.py` - Ortak yardımcı fonksiyonlar.
  * `rbac.py` - Rol tabanlı erişim kontrolü kurulum fonksiyonları.

### `frontend/` Klasörü

Ana klasördeki `.html` dosyaları statik sayfalardır: `index.html`, `giris.html`, `kayit.html`, `abonelik.html`, `dashboard.html`, `sifremi-unuttum.html`, `reset-password.html` ve `prediction-display.html`. Bunlar Flask tarafından servis edilen basit arayüzleri içerir.

`static/` klasöründe istemci JavaScript kodları (`api.js`) ve diğer statik varlıklar bulunur.

Ek olarak `admin/promo-codes-advanced.html` dosyası React ve Tailwind kullanılarak hazırlanmış gelişmiş promosyon kodu oluşturma formu örneğini içerir.

### Diğer Klasörler

- `migrations/` - Alembic tarafından oluşturulacak veritabanı göç dosyaları için yer tutucu.
- `tests/` - Uygulamanın temel işlevlerini doğrulayan Pytest testleri.
- `scripts/` - Ortam kurulumuna yardımcı betikler. Burada ayrıca `crypto_ta.py`
  dosyası bulunur ve çevrimdışı modda örnek teknik analiz yapar.
### Dizin Yapısı

```text
.
├── backend/
│   ├── admin_panel/
│   ├── api/
│   ├── auth/
│   ├── payment/
│   ├── core/
│   ├── db/
│   ├── frontend/
│   ├── tasks/
│   ├── templates/
│   ├── utils/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── abonelik.html
│   ├── abonelik2.html
│   ├── dashboard.html
│   ├── prediction-display.html
│   ├── frontend-crypto-analysis-dashboard
│   ├── giris.html
│   ├── homepage-unregistered.html
│   ├── kayit.html
│   ├── reset-password.html
│   ├── sifremi-unuttum.html
│   ├── ytdcrypto-admin-dashboard
│   └── static/
├── migrations/
├── scripts/
├── tests/
├── wsgi.py
├── docker-compose.yml
├── README.md
├── LICENSE
├── .env.example
└── .env
```

## Katkı Rehberi

Projeye katkıda bulunmak isterseniz aşağıdaki adımları takip edebilirsiniz:

1. Depoyu çatallayın ve kendi hesabınıza kopyalayın.
2. Geliştirme için yeni bir dal (`git checkout -b özellik-adi`) oluşturun.
3. Yaptığınız değişiklikleri açık ve anlamlı commit mesajlarıyla kaydedin.
4. Değişikliklerinizi GitHub üzerinde bir **Pull Request** olarak gönderin.

Katkılarınız her zaman memnuniyetle karşılanır. Sorularınız için yeni bir konu
açabilir veya mevcut tartışmalara katılabilirsiniz.

## Lisans

Bu proje MIT lisansı altında sunulmaktadır. Ayrıntılar için `LICENSE` dosyasına
bakabilirsiniz.


