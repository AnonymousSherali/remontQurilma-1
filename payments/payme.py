"""Payme Merchant API (JSON-RPC). Payme bizning /payments/payme/ manzilimizga so'rov yuboradi.

Sozlash (.env):
    PAYMENT_PROVIDERS=payme (yoki payme,click)
    PAYME_MERCHANT_ID=...      Payme Business kabinetidan
    PAYME_KEY=...              kassa kaliti (test uchun test kaliti)
    PAYME_TEST=True            test.paycom.uz (sinov muhiti)

Payme kabinetida hisob maydoni (account) nomini `milestone_id` qilib sozlang.

DIQQAT: bu integratsiya Payme hujjatlari asosida yozilgan, lekin haqiqiy Payme
sinov muhitida (test.paycom.uz "Песочница") tekshirilmagan. Ishga tushirishdan
oldin sandbox'dagi barcha testlardan o'tkazing.

Payme summani tiyinda yuboradi (1 so'm = 100 tiyin).
"""

import base64
import binascii
import json
import time

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services
from .models import Milestone, Payment

TIMEOUT_MS = 12 * 60 * 60 * 1000  # yaratilgan, lekin to'lanmagan tranzaksiya 12 soatdan keyin eskiradi

ERR_AUTH = -32504
ERR_PARSE = -32700
ERR_METHOD = -32601
ERR_SYSTEM = -32400
ERR_AMOUNT = -31001
ERR_NOT_FOUND = -31003
ERR_CANNOT_CANCEL = -31007
ERR_CANNOT_PERFORM = -31008
ERR_ACCOUNT = -31050

MESSAGES = {
    ERR_AUTH: ('Недостаточно привилегий', "Ruxsat yo'q", 'Insufficient privileges'),
    ERR_PARSE: ('Ошибка разбора JSON', 'JSON xatosi', 'Parse error'),
    ERR_METHOD: ('Метод не найден', 'Metod topilmadi', 'Method not found'),
    ERR_SYSTEM: ('Системная ошибка', 'Tizim xatosi', 'System error'),
    ERR_AMOUNT: ('Неверная сумма', "Summa noto'g'ri", 'Invalid amount'),
    ERR_NOT_FOUND: ('Транзакция не найдена', 'Tranzaksiya topilmadi', 'Transaction not found'),
    ERR_CANNOT_CANCEL: ('Невозможно отменить: услуга оказана', "Bekor qilib bo'lmaydi", 'Cannot cancel'),
    ERR_CANNOT_PERFORM: ('Невозможно выполнить операцию', "Amalni bajarib bo'lmaydi", 'Cannot perform'),
    ERR_ACCOUNT: ('Счёт не найден или уже оплачен', "To'lov topilmadi yoki to'langan", 'Account not found'),
}


class PaymeError(Exception):
    def __init__(self, code, data=None):
        super().__init__(code)
        self.code = code
        self.data = data


def _now_ms():
    return int(time.time() * 1000)


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt else 0


def checkout_url(milestone, return_url):
    params = (
        f'm={settings.PAYME_MERCHANT_ID};ac.{settings.PAYME_ACCOUNT_KEY}={milestone.pk};'
        f'a={int(milestone.amount) * 100};c={return_url}'
    )
    host = 'https://test.paycom.uz' if settings.PAYME_TEST else 'https://checkout.paycom.uz'
    return f'{host}/{base64.b64encode(params.encode()).decode()}'


def _authorized(request):
    header = request.META.get('HTTP_AUTHORIZATION', '')
    if not header.startswith('Basic ') or not settings.PAYME_KEY:
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(':')
    except (binascii.Error, UnicodeDecodeError):
        return False
    return login == 'Paycom' and password == settings.PAYME_KEY


def _milestone_for(params):
    account = params.get('account') or {}
    try:
        milestone = Milestone.objects.select_related('order').get(pk=int(account.get(settings.PAYME_ACCOUNT_KEY)))
    except (TypeError, ValueError, Milestone.DoesNotExist):
        raise PaymeError(ERR_ACCOUNT, settings.PAYME_ACCOUNT_KEY)
    if milestone.state != Milestone.STATE_PENDING:
        raise PaymeError(ERR_ACCOUNT, settings.PAYME_ACCOUNT_KEY)
    if int(params.get('amount', -1)) != int(milestone.amount) * 100:
        raise PaymeError(ERR_AMOUNT)
    return milestone


def _payment(payme_id):
    try:
        return Payment.objects.select_for_update().get(provider=Payment.PROVIDER_PAYME, provider_id=payme_id)
    except Payment.DoesNotExist:
        raise PaymeError(ERR_NOT_FOUND)


def _cancel_expired(payment):
    payment.state = Payment.STATE_CANCELLED
    payment.reason = 4  # Payme: tranzaksiya muddati o'tgan
    payment.cancelled_at = timezone.now()
    payment.save(update_fields=['state', 'reason', 'cancelled_at'])


def check_perform(params):
    _milestone_for(params)
    return {'allow': True}


def create(params):
    payme_id = params.get('id')
    existing = Payment.objects.select_for_update().filter(provider=Payment.PROVIDER_PAYME, provider_id=payme_id).first()
    if existing:
        if existing.state != Payment.STATE_CREATED:
            raise PaymeError(ERR_CANNOT_PERFORM)
        if _now_ms() - existing.provider_time > TIMEOUT_MS:
            _cancel_expired(existing)
            raise PaymeError(ERR_CANNOT_PERFORM)
        return {'create_time': existing.provider_time, 'transaction': str(existing.pk), 'state': existing.state}

    milestone = _milestone_for(params)
    # Bitta bosqich uchun bir vaqtda faqat bitta ochiq tranzaksiya
    if milestone.payments.filter(provider=Payment.PROVIDER_PAYME, state=Payment.STATE_CREATED).exists():
        raise PaymeError(ERR_ACCOUNT, settings.PAYME_ACCOUNT_KEY)
    payment = Payment.objects.create(
        milestone=milestone, provider=Payment.PROVIDER_PAYME, provider_id=payme_id,
        amount=milestone.amount, provider_time=int(params.get('time', _now_ms())),
    )
    return {'create_time': payment.provider_time, 'transaction': str(payment.pk), 'state': payment.state}


def perform(params):
    payment = _payment(params.get('id'))
    if payment.state == Payment.STATE_PERFORMED:
        return {'transaction': str(payment.pk), 'perform_time': _ms(payment.performed_at), 'state': payment.state}
    if payment.state != Payment.STATE_CREATED:
        raise PaymeError(ERR_CANNOT_PERFORM)
    if _now_ms() - payment.provider_time > TIMEOUT_MS:
        _cancel_expired(payment)
        raise PaymeError(ERR_CANNOT_PERFORM)
    payment.state = Payment.STATE_PERFORMED
    payment.performed_at = timezone.now()
    payment.save(update_fields=['state', 'performed_at'])
    services.mark_held(payment.milestone)
    return {'transaction': str(payment.pk), 'perform_time': _ms(payment.performed_at), 'state': payment.state}


def cancel(params):
    payment = _payment(params.get('id'))
    if payment.state in (Payment.STATE_CANCELLED, Payment.STATE_CANCELLED_AFTER_PERFORM):
        return {'transaction': str(payment.pk), 'cancel_time': _ms(payment.cancelled_at), 'state': payment.state}
    if payment.state == Payment.STATE_PERFORMED:
        milestone = payment.milestone
        if milestone.state == Milestone.STATE_RELEASED:
            raise PaymeError(ERR_CANNOT_CANCEL)  # pul allaqachon ustaga chiqarilgan
        payment.state = Payment.STATE_CANCELLED_AFTER_PERFORM
        if milestone.state == Milestone.STATE_HELD:
            services.refund(milestone)
    else:
        payment.state = Payment.STATE_CANCELLED
    payment.reason = params.get('reason')
    payment.cancelled_at = timezone.now()
    payment.save(update_fields=['state', 'reason', 'cancelled_at'])
    return {'transaction': str(payment.pk), 'cancel_time': _ms(payment.cancelled_at), 'state': payment.state}


def check(params):
    payment = _payment(params.get('id'))
    return {
        'create_time': payment.provider_time, 'perform_time': _ms(payment.performed_at),
        'cancel_time': _ms(payment.cancelled_at), 'transaction': str(payment.pk),
        'state': payment.state, 'reason': payment.reason,
    }


def statement(params):
    start, end = int(params.get('from', 0)), int(params.get('to', 0))
    rows = Payment.objects.filter(provider=Payment.PROVIDER_PAYME, provider_time__gte=start, provider_time__lte=end)
    return {'transactions': [{
        'id': p.provider_id, 'time': p.provider_time, 'amount': int(p.amount) * 100,
        'account': {settings.PAYME_ACCOUNT_KEY: str(p.milestone_id)},
        'create_time': p.provider_time, 'perform_time': _ms(p.performed_at), 'cancel_time': _ms(p.cancelled_at),
        'transaction': str(p.pk), 'state': p.state, 'reason': p.reason,
    } for p in rows.order_by('provider_time')]}


METHODS = {
    'CheckPerformTransaction': check_perform,
    'CreateTransaction': create,
    'PerformTransaction': perform,
    'CancelTransaction': cancel,
    'CheckTransaction': check,
    'GetStatement': statement,
}


def _error(code, request_id, data=None):
    ru, uz, en = MESSAGES.get(code, MESSAGES[ERR_SYSTEM])
    error = {'code': code, 'message': {'ru': ru, 'uz': uz, 'en': en}}
    if data:
        error['data'] = data
    # Payme JSON-RPC xatolarni ham HTTP 200 bilan kutadi
    return JsonResponse({'error': error, 'id': request_id})


@csrf_exempt
@require_POST
def endpoint(request):
    try:
        body = json.loads(request.body or b'{}')
    except ValueError:
        return _error(ERR_PARSE, None)
    request_id = body.get('id')
    if not _authorized(request):
        return _error(ERR_AUTH, request_id)
    method = METHODS.get(body.get('method'))
    if method is None:
        return _error(ERR_METHOD, request_id, body.get('method'))
    error = None
    with transaction.atomic():
        try:
            result = method(body.get('params') or {})
        except PaymeError as exc:
            # Xatoni atomic blok ICHIDA ushlaymiz: aks holda rollback bo'lib, masalan
            # muddati o'tgan tranzaksiyaning "bekor qilindi" holati saqlanmay qoladi.
            error = exc
    if error is not None:
        return _error(error.code, request_id, error.data)
    return JsonResponse({'result': result, 'id': request_id})
