"""SMS yuborish backendlari.

settings.SMS_BACKEND:
    'console' — SMS konsolga (server logiga) yoziladi. Ishlab chiqish uchun.
    'eskiz'   — Eskiz.uz (O'zbekistondagi eng ko'p ishlatiladigan SMS shlyuz).
                .env: ESKIZ_EMAIL, ESKIZ_PASSWORD, SMS_SENDER (masalan 4546).

Diqqat: Eskiz matn shablonlarini oldindan moderatsiyadan o'tkazishni talab qiladi.
otp/services.py va repair_service/customer_notify.py dagi matnlarni Eskiz
kabinetida shablon sifatida tasdiqlating, aks holda SMS yuborilmaydi.
"""

import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

ESKIZ_BASE = 'https://notify.eskiz.uz/api'
ESKIZ_TOKEN_CACHE_KEY = 'eskiz-token'


class SmsError(Exception):
    pass


class ConsoleBackend:
    sent = []  # testlar uchun

    def send(self, phone, text):
        logger.warning('SMS -> %s: %s', phone, text)
        print(f'[SMS] {phone}: {text}', flush=True)
        ConsoleBackend.sent.append((phone, text))


class EskizBackend:
    def _post(self, path, data, token=None):
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(f'{ESKIZ_BASE}{path}', data=body, method='POST')
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode() or '{}')

    def _token(self, refresh=False):
        token = None if refresh else cache.get(ESKIZ_TOKEN_CACHE_KEY)
        if token:
            return token
        data = self._post('/auth/login', {
            'email': settings.ESKIZ_EMAIL, 'password': settings.ESKIZ_PASSWORD,
        })
        token = (data.get('data') or {}).get('token')
        if not token:
            raise SmsError('Eskiz token olinmadi')
        cache.set(ESKIZ_TOKEN_CACHE_KEY, token, timeout=60 * 60 * 24 * 25)  # token ~30 kun amal qiladi
        return token

    def send(self, phone, text):
        payload = {
            'mobile_phone': phone.lstrip('+'),
            'message': text,
            'from': settings.SMS_SENDER,
        }
        try:
            self._post('/message/sms/send', payload, self._token())
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise SmsError(f'Eskiz xatosi: {error.code}') from error
            # Token eskirgan — bir marta yangilab qayta urinamiz
            self._post('/message/sms/send', payload, self._token(refresh=True))


def get_backend():
    name = getattr(settings, 'SMS_BACKEND', 'console')
    if name == 'eskiz':
        return EskizBackend()
    return ConsoleBackend()


def send_sms(phone, text, background=False):
    """SMS yuborish. background=True — xabarnomalar uchun (javobni kutmaymiz)."""
    backend = get_backend()

    def _run():
        try:
            backend.send(phone, text)
        except Exception:  # SMS xatosi asosiy jarayonni buzmasligi kerak
            logger.exception('SMS yuborilmadi: %s', phone)
            if not background:
                raise

    if background and not isinstance(backend, ConsoleBackend):
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()
