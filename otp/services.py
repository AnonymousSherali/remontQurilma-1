"""Bir martalik SMS kodlar: yuborish, tekshirish, sessiyada tasdiqlangan raqamlar.

Himoya:
- kod 5 daqiqa amal qiladi, 5 ta noto'g'ri urinishdan keyin bekor bo'ladi;
- bitta raqamga 60 soniyada 1 marta, soatiga 5 martadan ko'p yuborilmaydi
  (SMS pul turadi va bot orqali "SMS-bomba" qilish mumkin);
- bitta IP'dan soatiga 20 tadan ko'p emas.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import PhoneCode
from .sms import send_sms

CODE_TTL = timedelta(minutes=5)
RESEND_INTERVAL = timedelta(seconds=60)
MAX_PER_HOUR_PHONE = 5
MAX_PER_HOUR_IP = 20
MAX_ATTEMPTS = 5
SESSION_KEY = 'verified_phones'


class OtpError(Exception):
    pass


def _generate_code():
    return f'{secrets.randbelow(10 ** 6):06d}'


def send_code(phone, purpose, ip=None):
    """Kod yaratib SMS yuboradi. Qaytaradi: kod (faqat testlar/dev uchun ishlatiladi)."""
    now = timezone.now()
    recent = PhoneCode.objects.filter(phone=phone, created_at__gte=now - timedelta(hours=1))
    last = recent.order_by('-created_at').first()
    if last and now - last.created_at < RESEND_INTERVAL:
        wait = int((RESEND_INTERVAL - (now - last.created_at)).total_seconds()) + 1
        raise OtpError(_('Kodni qayta yuborish uchun %(sec)s soniya kuting') % {'sec': wait})
    if recent.count() >= MAX_PER_HOUR_PHONE:
        raise OtpError(_("Bu raqamga juda ko'p kod yuborildi. Bir soatdan keyin urinib ko'ring."))
    if ip and PhoneCode.objects.filter(ip=ip, created_at__gte=now - timedelta(hours=1)).count() >= MAX_PER_HOUR_IP:
        raise OtpError(_("Juda ko'p so'rov. Keyinroq urinib ko'ring."))

    # Eski faol kodlarni bekor qilamiz — faqat oxirgisi ishlaydi
    PhoneCode.objects.filter(phone=phone, purpose=purpose, is_used=False).update(is_used=True)

    code = _generate_code()
    PhoneCode.objects.create(
        phone=phone, purpose=purpose, code_hash=make_password(code), ip=ip, expires_at=now + CODE_TTL,
    )
    site = settings.SITE_INFO.get('name', '')
    send_sms(phone, _('%(site)s: tasdiqlash kodi %(code)s. Hech kimga aytmang.') % {'site': site, 'code': code})
    return code


def verify_code(phone, code, purpose):
    """Kodni tekshiradi. Noto'g'ri bo'lsa OtpError."""
    record = (
        PhoneCode.objects.filter(phone=phone, purpose=purpose, is_used=False, expires_at__gt=timezone.now())
        .order_by('-created_at').first()
    )
    if record is None:
        raise OtpError(_("Kod muddati o'tgan yoki yuborilmagan. Yangi kod oling."))
    if record.attempts >= MAX_ATTEMPTS:
        raise OtpError(_("Urinishlar soni tugadi. Yangi kod oling."))

    record.attempts += 1
    code = (code or '').strip()
    ok = len(code) == 6 and check_password(code, record.code_hash)  # check_password doimiy vaqtda solishtiradi
    if ok:
        record.is_used = True
    record.save(update_fields=['attempts', 'is_used'])
    if not ok:
        left = MAX_ATTEMPTS - record.attempts
        raise OtpError(_("Kod noto'g'ri. Qolgan urinishlar: %(n)s") % {'n': left})
    return True


# ---------- Sessiya: qaysi raqamlar shu brauzerda tasdiqlangan ----------

def mark_verified(request, phone, purpose=PhoneCode.PURPOSE_LOGIN):
    data = request.session.get(SESSION_KEY, {})
    data[f'{purpose}:{phone}'] = timezone.now().timestamp()
    request.session[SESSION_KEY] = data


def is_verified(request, phone, purpose=PhoneCode.PURPOSE_LOGIN, max_age=timedelta(hours=12)):
    stamp = request.session.get(SESSION_KEY, {}).get(f'{purpose}:{phone}')
    if not stamp:
        return False
    return timezone.now().timestamp() - stamp <= max_age.total_seconds()


def verified_phones(request, purpose=PhoneCode.PURPOSE_LOGIN):
    prefix = f'{purpose}:'
    return [key[len(prefix):] for key in request.session.get(SESSION_KEY, {}) if key.startswith(prefix)
            and is_verified(request, key[len(prefix):], purpose)]


def forget(request):
    request.session.pop(SESSION_KEY, None)
