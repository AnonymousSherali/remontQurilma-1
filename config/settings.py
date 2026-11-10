"""
Django settings for TechService project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path):
    """.env faylini o'qib, muhit o'zgaruvchilariga yozadi.

    Tashqi kutubxonaga bog'liq emas. Allaqachon mavjud muhit o'zgaruvchilari
    ustidan yozilmaydi — serverdagi haqiqiy sozlama har doim ustun turadi.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv(BASE_DIR / '.env')

# --- Security ---
# Production uchun: .env faylga ko'chiring yoki muhit o'zgaruvchisi qiling
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-w@shm@ch1ne-rep@1r-serv1ce-k3y-ch@nge-1n-pr0duct10n'
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

_allowed = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()] or (['*'] if DEBUG else [])

# --- Applications ---
INSTALLED_APPS = [
    'unfold',  # zamonaviy admin dizayni — django.contrib.admin dan oldin turishi shart
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # narxlarni ajratuvchi bilan chiqarish uchun
    'repair_service',
    'masters',
    'otp',
    'payments',
    'telegram_bot',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # til: /ru/ prefiksi yoki tanlangan til
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'repair_service.context_processors.site',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- Database ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# --- Kesh (spamdan himoya hisoblagichlari uchun) ---
# Bir nechta gunicorn worker bo'lsa, Redis yoki ma'lumotlar bazasi keshiga o'tkazing:
# LocMem har bir jarayonda alohida bo'ladi.
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# --- Password validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = 'uz'
LANGUAGES = [
    ('uz', "O'zbekcha"),
    ('ru', 'Русский'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

# --- Static & Media files ---
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- Default primary key ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- CSRF ---
_csrf = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [h.strip() for h in _csrf.split(',') if h.strip()]

# --- Production xavfsizligi ---
# Faqat DEBUG=False bo'lganda yoqiladi, shunda lokal ishlash buzilmaydi.
if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'True') == 'True'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', 31536000))  # 1 yil
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    # Nginx/reverse-proxy orqasida HTTPS ni to'g'ri aniqlash uchun
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# --- Kirish ---
LOGIN_URL = 'masters:login'
LOGIN_REDIRECT_URL = 'masters:dashboard'
LOGOUT_REDIRECT_URL = 'repair_service:index'

# --- Sayt kontaktlari (shablonlarda {{ SITE.phone }} va h.k.) ---
# Haqiqiy ma'lumotlarni .env orqali kiriting — standart qiymatlar namunaviy!
SITE_INFO = {
    'name': os.environ.get('SITE_NAME', 'TechService'),
    'phone': os.environ.get('SITE_PHONE', '+998901234567'),
    'email': os.environ.get('SITE_EMAIL', 'info@techservice.uz'),
    'address': os.environ.get('SITE_ADDRESS', 'Toshkent shahar'),
    'telegram': os.environ.get('SITE_TELEGRAM', ''),  # masalan: techservice_uz
    'hours': os.environ.get('SITE_HOURS', "Har kuni 08:00–22:00"),
}

# Saytning to'liq manzili — SMS'dagi havolalar uchun (https://techservice.uz)
SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')

# --- SMS (otp/sms.py) ---
SMS_BACKEND = os.environ.get('SMS_BACKEND', 'console')  # console | eskiz
ESKIZ_EMAIL = os.environ.get('ESKIZ_EMAIL', '')
ESKIZ_PASSWORD = os.environ.get('ESKIZ_PASSWORD', '')
SMS_SENDER = os.environ.get('SMS_SENDER', '4546')

# --- To'lovlar (payments) ---
# Mijozga taklif qilinadigan tizimlar, vergul bilan: demo | payme | click
PAYMENT_PROVIDERS = os.environ.get('PAYMENT_PROVIDERS', os.environ.get('PAYMENT_PROVIDER', 'demo'))
ALLOW_DEMO_PAYMENTS = os.environ.get('ALLOW_DEMO_PAYMENTS', 'False') == 'True'
PLATFORM_FEE_PERCENT = float(os.environ.get('PLATFORM_FEE_PERCENT', 10))
AUTO_CONFIRM_HOURS = int(os.environ.get('AUTO_CONFIRM_HOURS', 72))
AUTO_RELEASE_HOURS = int(os.environ.get('AUTO_RELEASE_HOURS', 48))
PAYME_MERCHANT_ID = os.environ.get('PAYME_MERCHANT_ID', '')
PAYME_KEY = os.environ.get('PAYME_KEY', '')
PAYME_TEST = os.environ.get('PAYME_TEST', 'True') == 'True'
PAYME_ACCOUNT_KEY = os.environ.get('PAYME_ACCOUNT_KEY', 'milestone_id')
CLICK_SERVICE_ID = os.environ.get('CLICK_SERVICE_ID', '')
CLICK_MERCHANT_ID = os.environ.get('CLICK_MERCHANT_ID', '')
CLICK_SECRET_KEY = os.environ.get('CLICK_SECRET_KEY', '')
CLICK_MERCHANT_USER_ID = os.environ.get('CLICK_MERCHANT_USER_ID', '')
UZUM_SERVICE_ID = os.environ.get('UZUM_SERVICE_ID', '')
UZUM_LOGIN = os.environ.get('UZUM_LOGIN', '')
UZUM_PASSWORD = os.environ.get('UZUM_PASSWORD', '')
UZUM_ACCOUNT_KEY = os.environ.get('UZUM_ACCOUNT_KEY', 'account')

# --- Ustalar uchun tariflar (payments/tariffs.py). Narxlar namunaviy! ---
TARIFF_PRICES = {
    'top_7': int(os.environ.get('TARIFF_TOP_7_PRICE', 50000)),
    'top_30': int(os.environ.get('TARIFF_TOP_30_PRICE', 150000)),
    'pro_30': int(os.environ.get('TARIFF_PRO_30_PRICE', 200000)),
}
PRO_FEE_PERCENT = float(os.environ.get('PRO_FEE_PERCENT', 5))
# Yangi ochiq buyurtmani dastlab faqat PRO ustalar ola oladigan vaqt (daqiqa)
FEED_PRO_HEAD_START_MINUTES = int(os.environ.get('FEED_PRO_HEAD_START_MINUTES', 10))
ACTIVE_ORDERS_LIMIT = int(os.environ.get('ACTIVE_ORDERS_LIMIT', 5))
PRO_ACTIVE_ORDERS_LIMIT = int(os.environ.get('PRO_ACTIVE_ORDERS_LIMIT', 10))

# --- Kafolat ---
# Namunaviy qiymatlar: muddat va kompensatsiya chegarasini biznes egasi belgilaydi.
WARRANTY_DAYS = int(os.environ.get('WARRANTY_DAYS', 30))
# Usta shu vaqt ichida javob bermasa, mijoz murojaatni administratorga o'tkaza oladi
WARRANTY_RESPONSE_HOURS = int(os.environ.get('WARRANTY_RESPONSE_HOURS', 48))
# "Usta tuzatdi" holatida mijoz shuncha kun javob bermasa — murojaat yopiladi
WARRANTY_AUTO_CLOSE_DAYS = int(os.environ.get('WARRANTY_AUTO_CLOSE_DAYS', 7))
# Platforma to'laydigan kompensatsiyaning yuqori chegarasi (so'm)
GUARANTEE_MAX_AMOUNT = int(os.environ.get('GUARANTEE_MAX_AMOUNT', 1_000_000))

# --- Integratsiyalar (ixtiyoriy) ---
YANDEX_MAPS_API_KEY = os.environ.get('YANDEX_MAPS_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
TELEGRAM_BOT_USERNAME = os.environ.get('TELEGRAM_BOT_USERNAME', '')  # @ belgisisiz, masalan techservice_uz_bot
TELEGRAM_WEBHOOK_SECRET = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '')
REQUEST_RATE_LIMIT = int(os.environ.get('REQUEST_RATE_LIMIT', 5))  # 10 daqiqada bir IP'dan

# --- Yuklanadigan fayllar ---
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Admin dizayni (django-unfold) ---
from django.urls import reverse_lazy  # noqa: E402

UNFOLD = {
    'SITE_TITLE': 'TechService admin',
    'SITE_HEADER': 'TechService',
    'SITE_SUBHEADER': 'Boshqaruv paneli',
    'SITE_URL': '/',
    'SITE_SYMBOL': 'handyman',
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': True,
    'DASHBOARD_CALLBACK': 'config.dashboard.dashboard_callback',
    'COLORS': {
        'primary': {
            '50': '236 253 245', '100': '209 250 229', '200': '167 243 208', '300': '110 231 183',
            '400': '52 211 153', '500': '16 185 129', '600': '5 150 105', '700': '4 120 87',
            '800': '6 95 70', '900': '6 78 59', '950': '2 44 34',
        },
    },
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': False,
        'navigation': [
            {
                'title': 'Asosiy',
                'items': [
                    {'title': 'Boshqaruv paneli', 'icon': 'dashboard', 'link': reverse_lazy('admin:index')},
                    {
                        'title': 'Arizalar', 'icon': 'assignment',
                        'link': reverse_lazy('admin:repair_service_servicerequest_changelist'),
                        'badge': 'config.dashboard.badge_new_requests',
                    },
                ],
            },
            {
                'title': 'Ustalar',
                'items': [
                    {
                        'title': 'Ustalar', 'icon': 'engineering',
                        'link': reverse_lazy('admin:masters_master_changelist'),
                        'badge': 'config.dashboard.badge_pending_masters',
                    },
                    {'title': 'Kategoriyalar', 'icon': 'category',
                     'link': reverse_lazy('admin:masters_category_changelist')},
                    {'title': 'Baholar', 'icon': 'star', 'link': reverse_lazy('admin:masters_review_changelist')},
                    {'title': 'Ish rasmlari', 'icon': 'photo_library',
                     'link': reverse_lazy('admin:repair_service_orderphoto_changelist')},
                    {'title': 'Kafolat murojaatlari', 'icon': 'verified_user',
                     'link': reverse_lazy('admin:repair_service_warrantyclaim_changelist'),
                     'badge': 'config.dashboard.badge_escalated_claims'},
                ],
            },
            {
                'title': "To'lovlar",
                'items': [
                    {"title": "To'lov bosqichlari", 'icon': 'account_balance_wallet',
                     'link': reverse_lazy('admin:payments_milestone_changelist')},
                    {'title': 'Narx takliflari', 'icon': 'request_quote',
                     'link': reverse_lazy('admin:payments_quote_changelist')},
                    {'title': 'Tarif xaridlari', 'icon': 'workspace_premium',
                     'link': reverse_lazy('admin:payments_purchase_changelist')},
                    {'title': 'Tranzaksiyalar', 'icon': 'receipt_long',
                     'link': reverse_lazy('admin:payments_payment_changelist')},
                    {'title': 'SMS kodlar', 'icon': 'sms', 'link': reverse_lazy('admin:otp_phonecode_changelist')},
                ],
            },
            {
                'title': 'Sayt kontenti',
                'items': [
                    {'title': 'Narxlar', 'icon': 'sell', 'link': reverse_lazy('admin:repair_service_service_changelist')},
                    {'title': 'Brendlar', 'icon': 'verified', 'link': reverse_lazy('admin:repair_service_brand_changelist')},
                    {'title': "Sharhlar (qo'lda)", 'icon': 'reviews',
                     'link': reverse_lazy('admin:repair_service_testimonial_changelist')},
                ],
            },
            {
                'title': 'Foydalanuvchilar',
                'items': [
                    {'title': 'Foydalanuvchilar', 'icon': 'person', 'link': reverse_lazy('admin:auth_user_changelist')},
                    {'title': 'Guruhlar', 'icon': 'group', 'link': reverse_lazy('admin:auth_group_changelist')},
                ],
            },
        ],
    },
}
