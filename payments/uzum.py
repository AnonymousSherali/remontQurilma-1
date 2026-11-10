"""Uzum Bank Merchant API. Uzum bizning beshta manzilimizga POST (JSON) yuboradi:

    /payments/uzum/check/    to'lov mumkinligini tekshirish
    /payments/uzum/create/   tranzaksiya yaratish
    /payments/uzum/confirm/  to'lovni tasdiqlash
    /payments/uzum/reverse/  bekor qilish
    /payments/uzum/status/   holatni so'rash

Sozlash (.env): UZUM_SERVICE_ID, UZUM_LOGIN, UZUM_PASSWORD (Basic auth — Uzum bilan
kelishiladi), UZUM_ACCOUNT_KEY (hisob parametrining nomi, standart "account").

⚠️ DIQQAT: Uzum Bank rasmiy hujjatni faqat hisob menejeri orqali beradi (ochiq emas).
Bu kod protokolning umumiy ma'lum tuzilishi asosida yozilgan: maydon nomlari, xato
kodlari va checkout manzili Uzum bergan hujjat bilan SOLISHTIRILISHI SHART. Payme va
Click'dan farqli o'laroq, buni hujjat bilan tekshirib bo'lmadi.

Summa tiyinda (1 so'm = 100 tiyin).
"""

import base64
import binascii
import hmac
import json
import time
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import payables
from .models import Payment

ERR_ACCESS = '10001'
ERR_JSON = '10002'
ERR_OPERATION = '10003'
ERR_PARAMS = '10005'
ERR_SERVICE = '10006'
ERR_ACCOUNT = '10007'
ERR_ALREADY_PAID = '10008'
ERR_CANCELLED = '10009'
ERR_TRANS_EXISTS = '10010'
ERR_AMOUNT = '10011'
ERR_TRANS_NOT_FOUND = '10014'
ERR_CANNOT_REVERSE = '10017'

STATUS_BY_STATE = {
    Payment.STATE_CREATED: 'CREATED',
    Payment.STATE_PERFORMED: 'CONFIRMED',
    Payment.STATE_CANCELLED: 'REVERSED',
    Payment.STATE_CANCELLED_AFTER_PERFORM: 'REVERSED',
}


class UzumError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _now_ms():
    return int(time.time() * 1000)


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt else None


def checkout_url(payable, return_url):
    params = {
        'serviceId': settings.UZUM_SERVICE_ID,
        settings.UZUM_ACCOUNT_KEY: payable.key,
        'amount': int(payable.amount) * 100,
        'redirectUrl': return_url,
    }
    return 'https://www.uzumbank.uz/open-service?' + urlencode(params)


def _authorized(request):
    header = request.META.get('HTTP_AUTHORIZATION', '')
    if not header.startswith('Basic ') or not settings.UZUM_PASSWORD:
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(':')
    except (binascii.Error, UnicodeDecodeError):
        return False
    return hmac.compare_digest(login, settings.UZUM_LOGIN) and hmac.compare_digest(password, settings.UZUM_PASSWORD)


def _payable(body, lock=False):
    key = (body.get('params') or {}).get(settings.UZUM_ACCOUNT_KEY)
    payable = payables.resolve(key, lock=lock)
    if payable is None:
        raise UzumError(ERR_ACCOUNT)
    return payable


def _payment(body):
    trans_id = body.get('transId')
    if not trans_id:
        raise UzumError(ERR_PARAMS)
    try:
        return Payment.objects.select_for_update().get(provider=Payment.PROVIDER_UZUM, provider_id=str(trans_id))
    except Payment.DoesNotExist:
        raise UzumError(ERR_TRANS_NOT_FOUND)


def _data(payable):
    return {settings.UZUM_ACCOUNT_KEY: {'value': payable.key}}


def check(body):
    payable = _payable(body)
    if not payable.is_pending:
        raise UzumError(ERR_ALREADY_PAID)
    return {'status': 'OK', 'data': _data(payable)}


def create(body):
    trans_id = body.get('transId')
    if not trans_id or body.get('amount') is None:
        raise UzumError(ERR_PARAMS)
    if Payment.objects.filter(provider=Payment.PROVIDER_UZUM, provider_id=str(trans_id)).exists():
        raise UzumError(ERR_TRANS_EXISTS)
    payable = _payable(body, lock=True)
    if not payable.is_pending:
        raise UzumError(ERR_ALREADY_PAID)
    try:
        amount = int(body['amount'])
    except (TypeError, ValueError):
        raise UzumError(ERR_AMOUNT)
    if amount != int(payable.amount) * 100:
        raise UzumError(ERR_AMOUNT)
    payment = Payment.objects.create(
        provider=Payment.PROVIDER_UZUM, provider_id=str(trans_id), amount=payable.amount,
        provider_time=_now_ms(), **payable.fk,
    )
    return {'transId': trans_id, 'status': 'CREATED', 'transTime': payment.provider_time,
            'data': _data(payable), 'amount': amount}


def confirm(body):
    payment = _payment(body)
    payable = payables.for_payment(payment)
    if payment.state in (Payment.STATE_CANCELLED, Payment.STATE_CANCELLED_AFTER_PERFORM):
        raise UzumError(ERR_CANCELLED)
    if payment.state == Payment.STATE_CREATED:
        if not payable.is_pending:  # shu orada boshqa tizim orqali to'langan
            raise UzumError(ERR_ALREADY_PAID)
        payment.state = Payment.STATE_PERFORMED
        payment.performed_at = timezone.now()
        payment.save(update_fields=['state', 'performed_at'])
        payable.mark_paid()
    # Takroriy confirm — xuddi shu javob (idempotent)
    return {'transId': payment.provider_id, 'status': 'CONFIRMED', 'confirmTime': _ms(payment.performed_at),
            'data': _data(payable), 'amount': int(payment.amount) * 100}


def reverse(body):
    payment = _payment(body)
    payable = payables.for_payment(payment)
    if payment.state == Payment.STATE_PERFORMED:
        if payable.cancel_locked:
            raise UzumError(ERR_CANNOT_REVERSE)
        payment.state = Payment.STATE_CANCELLED_AFTER_PERFORM
        payable.cancel_paid()
    elif payment.state == Payment.STATE_CREATED:
        payment.state = Payment.STATE_CANCELLED
    if not payment.cancelled_at:
        payment.cancelled_at = timezone.now()
    payment.save(update_fields=['state', 'cancelled_at'])
    return {'transId': payment.provider_id, 'status': 'REVERSED', 'reverseTime': _ms(payment.cancelled_at),
            'data': _data(payable), 'amount': int(payment.amount) * 100}


def status(body):
    payment = _payment(body)
    payable = payables.for_payment(payment)
    return {'transId': payment.provider_id, 'status': STATUS_BY_STATE[payment.state],
            'transTime': payment.provider_time, 'confirmTime': _ms(payment.performed_at),
            'reverseTime': _ms(payment.cancelled_at), 'data': _data(payable), 'amount': int(payment.amount) * 100}


OPERATIONS = {'check': check, 'create': create, 'confirm': confirm, 'reverse': reverse, 'status': status}


def _fail(code, service_id=None, http=400):
    return JsonResponse({'serviceId': service_id, 'timestamp': _now_ms(), 'status': 'FAILED', 'errorCode': code},
                        status=http)


@csrf_exempt
@require_POST
def endpoint(request, operation):
    if not _authorized(request):
        return _fail(ERR_ACCESS, http=401)
    handler = OPERATIONS.get(operation)
    if handler is None:
        return _fail(ERR_OPERATION)
    try:
        body = json.loads(request.body or b'{}')
    except ValueError:
        return _fail(ERR_JSON)
    service_id = body.get('serviceId')
    if str(service_id) != str(settings.UZUM_SERVICE_ID) or not settings.UZUM_SERVICE_ID:
        return _fail(ERR_SERVICE, service_id)

    error = None
    with transaction.atomic():
        try:
            result = handler(body)
        except UzumError as exc:
            error = exc  # atomic ichida ushlaymiz — yozilgan holatlar rollback bo'lmasin
    if error is not None:
        return _fail(error.code, service_id)
    return JsonResponse({'serviceId': service_id, 'timestamp': _now_ms(), **result})
