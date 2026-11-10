"""Click Shop API. Click bizning /payments/click/prepare/ va /payments/click/complete/
manzillarimizga POST so'rov yuboradi (ikki bosqich: tayyorlash va yakunlash).

Sozlash (.env):
    CLICK_SERVICE_ID=...     Click kabinetidan
    CLICK_MERCHANT_ID=...
    CLICK_SECRET_KEY=...     imzo tekshirish uchun
    CLICK_MERCHANT_USER_ID=  (ixtiyoriy)

Click kabinetida Prepare URL: https://SAYT/payments/click/prepare/
                  Complete URL: https://SAYT/payments/click/complete/

merchant_trans_id = bosqich (Milestone) ID si. Summa so'mda ("150000.00").

DIQQAT: hujjat (docs.click.uz) asosida yozilgan va testlar bilan qoplangan, lekin
haqiqiy Click sinov muhitida tekshirilmagan. Ishga tushirishdan oldin Click bergan
test vositasi bilan Prepare/Complete'ning barcha holatlarini o'tkazing.
"""

import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import payables
from .models import Payment

ACTION_PREPARE = 0
ACTION_COMPLETE = 1

OK = 0
ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_ACTION = -3
ERR_ALREADY_PAID = -4
ERR_ORDER_NOT_FOUND = -5
ERR_TRANSACTION_NOT_FOUND = -6
ERR_REQUEST = -8
ERR_CANCELLED = -9

NOTES = {
    OK: 'Success', ERR_SIGN: 'SIGN CHECK FAILED!', ERR_AMOUNT: 'Incorrect parameter amount',
    ERR_ACTION: 'Action not found', ERR_ALREADY_PAID: 'Already paid', ERR_ORDER_NOT_FOUND: 'Order does not exist',
    ERR_TRANSACTION_NOT_FOUND: 'Transaction does not exist', ERR_REQUEST: 'Error in request from click',
    ERR_CANCELLED: 'Transaction cancelled',
}


def checkout_url(payable, return_url):
    params = {
        'service_id': settings.CLICK_SERVICE_ID,
        'merchant_id': settings.CLICK_MERCHANT_ID,
        'amount': f'{payable.amount:.2f}',
        'transaction_param': payable.key,
        'return_url': return_url,
    }
    if settings.CLICK_MERCHANT_USER_ID:
        params['merchant_user_id'] = settings.CLICK_MERCHANT_USER_ID
    return 'https://my.click.uz/services/pay?' + urlencode(params)


def make_sign(data, prepare_id=''):
    """md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id [+ merchant_prepare_id] + amount + action + sign_time)"""
    raw = (
        f"{data.get('click_trans_id', '')}{data.get('service_id', '')}{settings.CLICK_SECRET_KEY}"
        f"{data.get('merchant_trans_id', '')}{prepare_id}{data.get('amount', '')}"
        f"{data.get('action', '')}{data.get('sign_time', '')}"
    )
    return hashlib.md5(raw.encode()).hexdigest()


def _reply(data, error, **extra):
    body = {
        'click_trans_id': data.get('click_trans_id'),
        'merchant_trans_id': data.get('merchant_trans_id'),
        'error': error,
        'error_note': NOTES.get(error, 'Error'),
    }
    body.update(extra)
    return JsonResponse(body)


def _check_common(data, action, prepare_id=''):
    """Umumiy tekshiruvlar. Xato bo'lsa xato kodi, aks holda (None, payable)."""
    if not settings.CLICK_SECRET_KEY:
        return ERR_REQUEST, None
    if str(data.get('action')) != str(action):
        return ERR_ACTION, None
    if not hmac.compare_digest(make_sign(data, prepare_id), data.get('sign_string', '')):
        return ERR_SIGN, None
    if str(data.get('service_id')) != str(settings.CLICK_SERVICE_ID):
        return ERR_REQUEST, None
    payable = payables.resolve(data.get('merchant_trans_id'), lock=True)
    if payable is None:
        return ERR_ORDER_NOT_FOUND, None
    try:
        amount = Decimal(data.get('amount'))
    except (InvalidOperation, TypeError):
        return ERR_AMOUNT, None
    if amount != payable.amount:
        return ERR_AMOUNT, None
    return None, payable


@csrf_exempt
@require_POST
@transaction.atomic
def prepare(request):
    data = request.POST
    error, payable = _check_common(data, ACTION_PREPARE)
    if error is not None:
        return _reply(data, error)
    if not payable.is_pending:
        return _reply(data, ERR_ALREADY_PAID)

    payment, _created = Payment.objects.get_or_create(
        provider=Payment.PROVIDER_CLICK, provider_id=str(data.get('click_trans_id')),
        defaults={'amount': payable.amount, **payable.fk},
    )
    if payables.account_key(payment) != payable.key:
        return _reply(data, ERR_REQUEST)
    return _reply(data, OK, merchant_prepare_id=payment.pk)


@csrf_exempt
@require_POST
@transaction.atomic
def complete(request):
    data = request.POST
    prepare_id = data.get('merchant_prepare_id', '')
    error, payable = _check_common(data, ACTION_COMPLETE, prepare_id)
    if error is not None:
        return _reply(data, error)

    try:
        payment = Payment.objects.select_for_update().get(
            pk=int(prepare_id), provider=Payment.PROVIDER_CLICK, provider_id=str(data.get('click_trans_id')),
        )
    except (TypeError, ValueError, Payment.DoesNotExist):
        return _reply(data, ERR_TRANSACTION_NOT_FOUND)

    if payment.state == Payment.STATE_CANCELLED:
        return _reply(data, ERR_CANCELLED)
    if payment.state == Payment.STATE_PERFORMED:
        return _reply(data, ERR_ALREADY_PAID, merchant_confirm_id=payment.pk)

    # Click to'lovni o'z tomonida amalga oshira olmagan bo'lsa (error < 0) — bekor qilamiz
    try:
        click_error = int(data.get('error', 0))
    except ValueError:
        click_error = 0
    if click_error < 0:
        payment.state = Payment.STATE_CANCELLED
        payment.cancelled_at = timezone.now()
        payment.save(update_fields=['state', 'cancelled_at'])
        return _reply(data, ERR_CANCELLED, merchant_confirm_id=payment.pk)

    if not payable.is_pending:
        return _reply(data, ERR_ALREADY_PAID, merchant_confirm_id=payment.pk)

    payment.state = Payment.STATE_PERFORMED
    payment.performed_at = timezone.now()
    payment.save(update_fields=['state', 'performed_at'])
    payable.mark_paid()
    return _reply(data, OK, merchant_confirm_id=payment.pk)
