"""Mijozga pul qaytarish.

Qachon kerak: nizo mijoz foydasiga hal qilinganda yoki admin «Mijozga qaytarish» amalini bosganda —
bosqich «Qaytarildi» holatiga o'tadi va shu yerda qaytarish yozuvi (Refund) ochiladi.

Tizimlar bo'yicha:
- Click — CLICK_AUTO_REFUND=True bo'lsa, Click Merchant API orqali avtomatik (payment/reversal).
  Click qoidasi: faqat joriy hisobot oyida to'langan to'lovlar qaytariladi; aks holda — qo'lda.
- Payme — Merchant API'da do'kon tomonidan qaytarish so'rovi yo'q: kassir Payme Business
  kabinetida tranzaksiyani bekor qiladi, Payme bizga CancelTransaction yuboradi va qaytarish
  shu zahoti avtomatik «Qaytarildi» bo'ladi (on_provider_cancelled).
- Uzum — reverse so'rovi kelganda xuddi shunday; qolgan hollarda qo'lda.
- Demo — haqiqiy pul yo'q, darhol yopiladi.
Qolganlari admin → «Pul qaytarishlar» navbatida: tranzaksiya raqami, summa va ko'rsatma bilan.
"""

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Payment, Refund

logger = logging.getLogger(__name__)
CLICK_API = 'https://api.click.uz/v2/merchant'


def paid_payment(milestone):
    return (milestone.payments.filter(state__in=(Payment.STATE_PERFORMED, Payment.STATE_CANCELLED_AFTER_PERFORM))
            .order_by('-performed_at').first())


def instructions(refund):
    """Admin uchun: bu qaytarishni qanday bajarish."""
    payment = refund.payment
    if payment is None:
        return "To'lov tizimi orqali to'lov topilmadi — mijoz bilan bog'lanib, pulni boshqa yo'l bilan qaytaring."
    if payment.provider == Payment.PROVIDER_PAYME:
        return (f"Payme Business kabinetida tranzaksiya {payment.provider_id} ni bekor qiling — "
                "Payme bizga xabar beradi va bu yozuv o'zi «Qaytarildi» bo'ladi.")
    if payment.provider == Payment.PROVIDER_CLICK:
        doc = f' (to\'lov hujjati {payment.provider_doc_id})' if payment.provider_doc_id else ''
        return (f"Click merchant kabinetida to'lov {payment.provider_id}{doc} ni qaytaring yoki «Click orqali "
                "qaytarish» amalini bosing (CLICK_AUTO_REFUND).")
    if payment.provider == Payment.PROVIDER_UZUM:
        return f"Uzum Bank kabinetida tranzaksiya {payment.provider_id} ni bekor qiling."
    return 'Demo to\'lov — haqiqiy pul yo\'q.'


def request_refund(milestone, note=''):
    """Bosqich «Qaytarildi» bo'lgach chaqiriladi: yozuv ochadi va imkon bo'lsa avtomatik qaytaradi."""
    existing = milestone.refunds.exclude(status=Refund.STATUS_FAILED).first()
    if existing:
        return existing
    payment = paid_payment(milestone)
    refund = Refund.objects.create(milestone=milestone, payment=payment, amount=milestone.amount_due, note=note[:500])
    if payment is None:
        return refund
    if payment.provider == Payment.PROVIDER_DEMO:
        return _done(refund, Refund.METHOD_AUTO, 'Demo')
    if payment.state == Payment.STATE_CANCELLED_AFTER_PERFORM:      # to'lov tizimi allaqachon bekor qilgan
        return _done(refund, Refund.METHOD_PROVIDER)
    if payment.provider == Payment.PROVIDER_CLICK and getattr(settings, 'CLICK_AUTO_REFUND', False):
        click_reversal(refund)
    return refund


def _done(refund, method, note=''):
    refund.status, refund.method, refund.done_at = Refund.STATUS_DONE, method, timezone.now()
    if note:
        refund.note = (refund.note + ' ' + note).strip()[:500]
    refund.save(update_fields=['status', 'method', 'done_at', 'note'])
    transaction.on_commit(lambda: _notify_customer(refund))
    return refund


def mark_manual(refund, note=''):
    if refund.status == Refund.STATUS_DONE:
        return refund
    return _done(refund, Refund.METHOD_MANUAL, note)


def on_provider_cancelled(payment):
    """To'lov tizimi to'langan tranzaksiyani bekor qildi (kassir kabinetdan qaytardi)."""
    if payment.milestone_id is None:
        return None
    refund = Refund.objects.filter(payment=payment).exclude(status=Refund.STATUS_DONE).first() or \
        Refund.objects.filter(milestone_id=payment.milestone_id, status__in=(Refund.STATUS_PENDING,
                                                                              Refund.STATUS_FAILED)).first()
    if refund is None:
        refund = Refund.objects.create(milestone_id=payment.milestone_id, payment=payment, amount=payment.amount,
                                       note="To'lov tizimi tomonidan bekor qilindi")
    refund.payment = payment
    refund.save(update_fields=['payment'])
    return _done(refund, Refund.METHOD_PROVIDER)


def click_reversal(refund):
    """Click Merchant API: DELETE /payment/reversal/{service_id}/{payment_id}.

    Auth: merchant_user_id:sha1(timestamp + secret_key):timestamp. Muvaffaqiyat — error_code == 0.
    """
    payment = refund.payment
    timestamp = str(int(time.time()))
    digest = hashlib.sha1((timestamp + settings.CLICK_SECRET_KEY).encode()).hexdigest()
    url = f'{CLICK_API}/payment/reversal/{settings.CLICK_SERVICE_ID}/{payment.provider_id}'
    request = urllib.request.Request(url, method='DELETE', headers={
        'Accept': 'application/json', 'Content-Type': 'application/json',
        'Auth': f'{settings.CLICK_MERCHANT_USER_ID}:{digest}:{timestamp}'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode() or '{}')
    except urllib.error.HTTPError as error:
        data = {'error_code': error.code, 'error_note': f'HTTP {error.code}'}
    except Exception as error:  # noqa: BLE001
        logger.exception('Click reversal')
        data = {'error_code': -1, 'error_note': str(error)[:200]}
    if str(data.get('error_code')) == '0':
        Payment.objects.filter(pk=payment.pk).update(state=Payment.STATE_CANCELLED_AFTER_PERFORM,
                                                     cancelled_at=timezone.now())
        return _done(refund, Refund.METHOD_AUTO, 'Click API')
    refund.status = Refund.STATUS_FAILED
    refund.note = (f"Click: {data.get('error_code')} {data.get('error_note', '')} — kabinetdan qo'lda qaytaring. "
                   + refund.note)[:500]
    refund.save(update_fields=['status', 'note'])
    return refund


def _notify_customer(refund):
    from repair_service import customer_notify
    order = refund.milestone.order
    with translation.override(order.language or 'uz'):
        text = _("%(amount)s so'm qaytarildi (#%(id)s buyurtma). Pul kartangizga to'lov tizimi qoidalariga ko'ra "
                 "tushadi. %(url)s") % {'amount': f'{int(refund.amount):,}'.replace(',', ' '), 'id': order.pk,
                                        'url': customer_notify._customer_link(order)}
        customer_notify._to_customer(order, text)


def pending_count():
    return Refund.objects.exclude(status=Refund.STATUS_DONE).count()

