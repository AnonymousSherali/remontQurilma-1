"""Mijoz buyurtmasini Telegram chatga ulash kodi.

Buyurtma havolasi (review_token) faqat ko'rish uchun — u yuborilgan yoki tarixda qolgan bo'lishi
mumkin. Shuning uchun bot ulash uchun alohida, imzolangan va 30 daqiqa amal qiladigan kod
ishlatiladi; uni faqat SMS-kod bilan tasdiqlangan brauzer oladi.
Telegram start parametri: faqat A-Z a-z 0-9 _ -, 64 belgigacha.
"""

import hashlib
import hmac
import time

from django.conf import settings

TTL_SECONDS = 30 * 60


def _sign(order_id, ts):
    key = ('telegram-order-link:' + settings.SECRET_KEY).encode()
    return hmac.new(key, f'{order_id}-{ts}'.encode(), hashlib.sha256).hexdigest()[:24]


def make(order, now=None):
    ts = int(now if now is not None else time.time())
    return f'o{order.pk}-{ts}-{_sign(order.pk, ts)}'


def parse(param, now=None):
    """Kod to'g'ri va eskirmagan bo'lsa buyurtma id, aks holda None."""
    try:
        order_id, ts, signature = param[1:].split('-')
        order_id, ts = int(order_id), int(ts)
    except ValueError:
        return None
    now = int(now if now is not None else time.time())
    if not 0 <= now - ts <= TTL_SECONDS:
        return None
    return order_id if hmac.compare_digest(signature, _sign(order_id, ts)) else None
