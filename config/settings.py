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
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # narxlarni ajratuvchi bilan chiqarish uchun
    'repair_service',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
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

# --- Password validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = 'uz'
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
