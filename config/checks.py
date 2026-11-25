"""Ishga tushirishdan oldingi tekshiruvlar: python manage.py check --deploy

Django'ning o'z xavfsizlik tekshiruvlariga qo'shimcha — loyihaning o'ziga xos
sozlamalari production uchun yaroqliligini tekshiradi.
"""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def production_settings(app_configs, **kwargs):
    issues = []
    backend = settings.CACHES['default']['BACKEND']
    if backend.endswith('LocMemCache'):
        issues.append(Warning(
            "Kesh — LocMem: har bir gunicorn worker'da alohida, SMS va spam cheklovlari ishonchsiz ishlaydi.",
            hint="REDIS_URL=redis://127.0.0.1:6379/1 yoki DJANGO_CACHE=db (keyin: manage.py createcachetable).",
            id='techservice.W001'))
    if settings.DATABASES['default']['ENGINE'].endswith('sqlite3'):
        issues.append(Warning(
            "Ma'lumotlar bazasi — SQLite: bir vaqtdagi yozuvlarda bloklanadi, select_for_update ishlamaydi.",
            hint='DATABASE_URL=postgres://foydalanuvchi:parol@127.0.0.1:5432/techservice', id='techservice.W002'))
    if getattr(settings, 'SMS_BACKEND', 'console') == 'console':
        issues.append(Warning(
            "SMS_BACKEND=console: tasdiqlash kodlari faqat logga yoziladi — mijoz va ustalar kod olmaydi.",
            hint='SMS_BACKEND=eskiz va ESKIZ_EMAIL / ESKIZ_PASSWORD ni sozlang.', id='techservice.W003'))
    if not settings.SITE_URL.startswith('https://'):
        issues.append(Warning(
            f"SITE_URL={settings.SITE_URL}: SMS va Telegram'dagi havolalar shu manzilga olib boradi.",
            hint='SITE_URL=https://sizning-domeningiz.uz', id='techservice.W004'))
    providers = [p.strip() for p in settings.PAYMENT_PROVIDERS.split(',') if p.strip()]
    if providers == ['demo'] or not providers:
        issues.append(Warning(
            "PAYMENT_PROVIDERS=demo: haqiqiy to'lov tizimi ulanmagan, onlayn to'lov ishlamaydi.",
            hint="PAYMENT_PROVIDERS=payme,click (ulangan tizimlar).", id='techservice.W005'))
    if getattr(settings, 'ALLOW_DEMO_PAYMENTS', False):
        issues.append(Warning(
            "ALLOW_DEMO_PAYMENTS=True: istalgan odam bosqichni pulsiz «to'langan» qilib qo'ya oladi.",
            hint='Production\'da ALLOW_DEMO_PAYMENTS=False.', id='techservice.W006'))
    if getattr(settings, 'LEGAL_DRAFT', True):
        issues.append(Warning(
            'Oferta va maxfiylik siyosati — loyiha (LEGAL_DRAFT=True), saytda «Loyiha» belgisi chiqadi.',
            hint='Yurist tasdiqlagach LEGAL_DRAFT=False va SITE_LEGAL_* ni to\'ldiring.', id='techservice.W007'))
    private = settings.PRIVATE_MEDIA_ROOT.resolve()
    if private == settings.MEDIA_ROOT.resolve() or settings.MEDIA_ROOT.resolve() in private.parents:
        issues.append(Warning(
            "PRIVATE_MEDIA_ROOT MEDIA_ROOT ichida — ustalarning hujjatlari ochiq havola orqali ko'rinib qolishi mumkin.",
            hint='DJANGO_PRIVATE_MEDIA_ROOT ni MEDIA_ROOT dan tashqariga qo\'ying.', id='techservice.W008'))
    return issues
