"""Web Push (brauzer bildirishnomalari) — tashqi kutubxonasiz, faqat `cryptography` bilan.

Standartlar: RFC 8291 (xabarni shifrlash, aes128gcm), RFC 8292 (VAPID — server imzosi).
pywebpush ishlatilmadi: uning http-ece bog'liqligi ko'p serverlarda o'rnatilmaydi.

Kalitlar: python manage.py webpush_keys  → .env ga WEBPUSH_PUBLIC_KEY / WEBPUSH_PRIVATE_KEY.
Kalit bo'lmasa push o'chiq — saytda «Bildirishnomalar» tugmasi chiqmaydi.

Xavfsizlik: obuna manzili (endpoint) brauzerdan keladi va server unga POST yuboradi —
shuning uchun faqat ma'lum push xizmatlari domenlariga ruxsat beriladi (SSRF dan himoya).
"""

import base64
import json
import logging
import os
import struct
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from django.conf import settings

logger = logging.getLogger(__name__)

# Brauzerlarning push xizmatlari (Chrome/Edge/Yandex — FCM, Firefox — Mozilla, Safari — Apple, eski Edge — WNS)
ALLOWED_HOST_SUFFIXES = ('fcm.googleapis.com', 'android.googleapis.com', 'push.services.mozilla.com',
                         'push.apple.com', 'notify.windows.com')
SENT = []   # testlar uchun (kalit sozlanmagan bo'lsa ham yozib boriladi)


class PushError(Exception):
    pass


def b64u_decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def b64u_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def enabled():
    return bool(getattr(settings, 'WEBPUSH_PUBLIC_KEY', '') and getattr(settings, 'WEBPUSH_PRIVATE_KEY', ''))


def endpoint_allowed(endpoint):
    try:
        parsed = urlparse(endpoint)
    except ValueError:
        return False
    host = (parsed.hostname or '').lower()
    return parsed.scheme == 'https' and any(host == s or host.endswith('.' + s) for s in ALLOWED_HOST_SUFFIXES)


def generate_keys():
    """(public, private) — base64url: ochiq kalit 65 bayt (siqilmagan nuqta), maxfiy — 32 bayt."""
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, 'big')
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64u_encode(public), b64u_encode(private)


def _hkdf_expand(prk, info, length):
    return HKDFExpand(algorithm=hashes.SHA256(), length=length, info=info).derive(prk)


def _hkdf_extract(salt, ikm):
    # HKDF-Extract (RFC 5869) = HMAC-SHA256(salt, ikm)
    h = hmac.HMAC(salt, hashes.SHA256())
    h.update(ikm)
    return h.finalize()


def encrypt(payload, p256dh, auth, salt=None, server_key=None):
    """RFC 8291: aes128gcm kodlashidagi xabar tanasi (sarlavha + shifrlangan matn)."""
    ua_public = b64u_decode(p256dh)
    auth_secret = b64u_decode(auth)
    if len(ua_public) != 65 or len(auth_secret) < 16:
        raise PushError("Obuna kalitlari noto'g'ri")
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public = server_key.public_key().public_bytes(serialization.Encoding.X962,
                                                     serialization.PublicFormat.UncompressedPoint)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh_secret = server_key.exchange(ec.ECDH(), ua_key)

    prk_key = _hkdf_extract(auth_secret, ecdh_secret)
    ikm = _hkdf_expand(prk_key, b'WebPush: info\x00' + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    prk = _hkdf_extract(salt, ikm)
    cek = _hkdf_expand(prk, b'Content-Encoding: aes128gcm\x00', 16)
    nonce = _hkdf_expand(prk, b'Content-Encoding: nonce\x00', 12)

    record_size = 4096
    plaintext = payload + b'\x02'          # yagona (oxirgi) yozuv chegarasi
    if len(plaintext) + 16 > record_size:
        raise PushError('Xabar juda uzun')
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext, None)
    header = salt + struct.pack('!L', record_size) + bytes([len(as_public)]) + as_public
    return header + ciphertext


def vapid_headers(endpoint):
    """RFC 8292: Authorization: vapid t=<JWT>, k=<ochiq kalit>."""
    parsed = urlparse(endpoint)
    private_value = int.from_bytes(b64u_decode(settings.WEBPUSH_PRIVATE_KEY), 'big')
    key = ec.derive_private_key(private_value, ec.SECP256R1())
    subject = getattr(settings, 'WEBPUSH_SUBJECT', '') or f"mailto:{settings.SITE_INFO['email']}"
    header = b64u_encode(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
    claims = b64u_encode(json.dumps({'aud': f'{parsed.scheme}://{parsed.netloc}',
                                     'exp': int(time.time()) + 12 * 3600, 'sub': subject},
                                    separators=(',', ':')).encode())
    signing_input = f'{header}.{claims}'.encode()
    r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    token = f'{header}.{claims}.{b64u_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}'
    return {'Authorization': f'vapid t={token}, k={settings.WEBPUSH_PUBLIC_KEY}'}


def send(subscription, title, body='', url='/', ttl=24 * 3600):
    """Bitta obunaga yuboradi. Qaytaradi: True — yuborildi, False — obuna eskirgan (o'chirildi) yoki xato."""
    payload = json.dumps({'title': str(title), 'body': str(body)[:300], 'url': url}, ensure_ascii=False).encode()
    SENT.append((subscription.endpoint, json.loads(payload)))
    if not enabled():
        return False
    if not endpoint_allowed(subscription.endpoint):
        subscription.delete()
        return False
    try:
        data = encrypt(payload, subscription.p256dh, subscription.auth)
        request = urllib.request.Request(subscription.endpoint, data=data, method='POST', headers={
            'Content-Encoding': 'aes128gcm', 'Content-Type': 'application/octet-stream',
            'TTL': str(ttl), 'Urgency': 'high', **vapid_headers(subscription.endpoint)})
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):       # foydalanuvchi obunani bekor qilgan yoki brauzer o'chirilgan
            subscription.delete()
        else:
            logger.warning('Web push %s: %s', error.code, subscription.endpoint[:60])
        return False
    except Exception:  # noqa: BLE001 — bildirishnoma asosiy jarayonni buzmasin
        logger.exception('Web push yuborilmadi')
        return False


def notify(subscriptions, title, body='', url='/'):
    """Bir nechta obunaga fon oqimida (sahifa kutmaydi)."""
    subs = list(subscriptions)
    if not subs:
        return
    absolute = url if url.startswith('http') else settings.SITE_URL.rstrip('/') + url

    def run():
        for sub in subs:
            send(sub, title, body, absolute)

    if enabled():
        threading.Thread(target=run, daemon=True).start()
    else:
        run()   # testlar va kalitsiz rejim: faqat SENT ga yoziladi
