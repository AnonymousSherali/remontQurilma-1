from django.conf import settings
from django.utils.translation import gettext as _

from .phone import format_phone


def _js_i18n():
    """app.js ichidagi matnlar — joriy tilda."""
    return {
        'resend': _('Qayta yuborish'),
        'debugCode': _('Sinov rejimi, kod:'),
        'network': _("Tarmoq xatosi. Qaytadan urinib ko'ring."),
        'fixErrors': _("Formadagi xatolarni to'g'rilang"),
        'genericError': _("Xatolik yuz berdi. Keyinroq urinib ko'ring."),
        'copied': _('Havola nusxalandi'),
        'locating': _('Aniqlanmoqda…'),
        'located': _('✓ Joylashuv aniqlandi'),
        'geoUnsupported': _('Brauzeringiz joylashuvni aniqlay olmaydi. Tumanni tanlang.'),
        'geoHttps': _('Joylashuv faqat HTTPS orqali ishlaydi. Hozircha tumanni tanlang.'),
        'geoDenied': _('Joylashuvga ruxsat berilmadi. Brauzer sozlamalaridan ruxsat bering yoki tumanni tanlang.'),
        'geoFailed': _("Joylashuvni aniqlab bo'lmadi. Tumanni tanlang."),
        'mapPicked': _('✓ Joylashuv xaritada belgilandi'),
        'reviews': _('baho'),
        'openProfile': _('Profilni ochish →'),
        'you': _('Siz'),
    }


def site(request):
    """Kontakt ma'lumotlari bitta joyda (settings.SITE_INFO / .env).

    Avval telefon raqami shablonning 6 joyida qo'lda yozilgan edi — birini
    o'zgartirib, qolganini unutish oson edi.
    """
    info = dict(settings.SITE_INFO)
    info['phone_display'] = format_phone(info.get('phone', ''))
    info['warranty_days'] = settings.WARRANTY_DAYS
    return {
        'SITE': info,
        'YANDEX_MAPS_API_KEY': getattr(settings, 'YANDEX_MAPS_API_KEY', ''),
        'js_i18n': _js_i18n(),
    }
