"""Yuridik shaxslar (ofis, do'kon, tashkilot) uchun: schyot orqali bank o'tkazmasi va dalolatnoma.

- Arizada «Tashkilot nomidan» bo'limi: nomi, STIR (9 raqam), yuridik manzil.
- Onlayn to'lov rejasida har bir to'lov bosqichi uchun «Bank o'tkazmasi» — to'lov uchun schyot
  (chop etiladigan sahifa: platforma rekvizitlari, buyurtmachi, summa, to'lov maqsadi).
- Pul hisobga tushganda administrator «Bank o'tkazmasi tushdi» amalini bosadi — bosqich
  «ushlab turilgan» bo'ladi va ish davom etadi (karta orqali to'lov bilan bir xil).
- Buyurtma tasdiqlangach — bajarilgan ishlar dalolatnomasi (chop etish uchun).

Muhim: bular buxgalteriya uchun hujjatlar. Elektron hisob-faktura (ESF) soliq tizimining operatori
(Didox, Faktura.uz va h.k.) orqali buxgalter tomonidan alohida rasmiylashtiriladi. Platforma modeli
(agent yoki ijrochi), QQS va hujjat shakllarini buxgalter/yurist bilan aniqlang.
"""

import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from payments.models import Milestone, Payment

INN_RE = re.compile(r'^\d{9}$')


class BusinessError(Exception):
    pass


def bank_enabled():
    info = settings.SITE_INFO
    return bool(info.get('bank_account') and info.get('bank_mfo') and info.get('legal_name') and info.get('legal_inn'))


def normalize_inn(value):
    return re.sub(r'\D', '', value or '')


def invoice_number(milestone):
    return f'TS-{milestone.order_id}-{milestone.position}'


def request_transfer(milestone):
    """Mijoz «Bank o'tkazmasi»ni tanladi: kutilayotgan to'lov yozuvi (bitta bosqichga bitta)."""
    if not bank_enabled():
        raise BusinessError("Bank o'tkazmasi sozlanmagan")
    if milestone.state != Milestone.STATE_PENDING:
        raise BusinessError("Bu bosqich allaqachon to'langan")
    payment, _created = Payment.objects.get_or_create(
        provider=Payment.PROVIDER_BANK, provider_id=invoice_number(milestone),
        defaults={'milestone': milestone, 'amount': milestone.amount_due})
    if payment.state == Payment.STATE_CREATED and payment.amount != milestone.amount_due:
        payment.amount = milestone.amount_due          # promo-kod keyin qo'shilgan bo'lsa
        payment.save(update_fields=['amount'])
    return payment


@transaction.atomic
def confirm_transfer(payment):
    """Administrator: pul bank hisobiga tushdi."""
    from payments import services
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.provider != Payment.PROVIDER_BANK or payment.state != Payment.STATE_CREATED:
        return False
    payment.state, payment.performed_at = Payment.STATE_PERFORMED, timezone.now()
    payment.save(update_fields=['state', 'performed_at'])
    services.mark_held(payment.milestone)
    from repair_service import workflow
    workflow.record(payment.milestone.order, payment.milestone.order.status, workflow.ADMIN,
                    note=f"Bank o'tkazmasi tushdi: {invoice_number(payment.milestone)}")
    return True


def vat(amount):
    """(QQS summasi, foiz) yoki (None, None) — QQSsiz."""
    raw = settings.SITE_INFO.get('vat_percent') or ''
    try:
        percent = float(raw)
    except ValueError:
        return None, None
    # Narx QQS bilan: QQS = summa × foiz / (100 + foiz)
    return round(float(amount) * percent / (100 + percent)), percent
