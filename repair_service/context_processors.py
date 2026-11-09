from django.conf import settings

from .phone import format_phone


def site(request):
    """Kontakt ma'lumotlari bitta joyda (settings.SITE_INFO / .env).

    Avval telefon raqami shablonning 6 joyida qo'lda yozilgan edi — birini
    o'zgartirib, qolganini unutish oson edi.
    """
    info = dict(settings.SITE_INFO)
    info['phone_display'] = format_phone(info.get('phone', ''))
    return {
        'SITE': info,
        'YANDEX_MAPS_API_KEY': getattr(settings, 'YANDEX_MAPS_API_KEY', ''),
    }
