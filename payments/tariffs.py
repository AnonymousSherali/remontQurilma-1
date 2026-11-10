"""Ustalar uchun pullik tariflar.

TOP — usta qidiruvda yuqorida, "TOP" belgisi bilan ko'rsatiladi (reklama ekani ochiq aytiladi).
PRO — komissiya kamayadi, ochiq buyurtmalar birinchi bo'lib keladi, bir vaqtda ko'proq buyurtma.

Narxlar NAMUNAVIY — .env orqali o'zgartiring (TARIFF_TOP_7_PRICE va h.k.).
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Purchase

KIND_TOP = 'top'
KIND_PRO = 'pro'

_PLANS = [
    # (kod, turi, kunlar, standart narx, nomi)
    ('top_7', KIND_TOP, 7, 50000, _('TOP — 7 kun')),
    ('top_30', KIND_TOP, 30, 150000, _('TOP — 30 kun')),
    ('pro_30', KIND_PRO, 30, 200000, _('PRO — 30 kun')),
]


def plans():
    overrides = getattr(settings, 'TARIFF_PRICES', {})
    return [
        {'code': code, 'kind': kind, 'days': days, 'price': int(overrides.get(code, price)), 'title': title}
        for code, kind, days, price, title in _PLANS
    ]


def get_plan(code):
    return next((p for p in plans() if p['code'] == code), None)


def create_purchase(master, code):
    plan = get_plan(code)
    if plan is None:
        raise ValueError(code)
    # Bir xil tarifga to'lanmagan eski urinishlar ortiqcha — yangisini ochamiz
    master.purchases.filter(plan=code, status=Purchase.STATUS_PENDING, payments__isnull=True).delete()
    return Purchase.objects.create(master=master, plan=code, kind=plan['kind'], days=plan['days'], amount=plan['price'])


@transaction.atomic
def activate(purchase):
    """To'lov o'tdi — muddatni uzaytiramiz (faol bo'lsa oxiridan, bo'lmasa hozirdan). Idempotent."""
    purchase = Purchase.objects.select_for_update().select_related('master').get(pk=purchase.pk)
    if purchase.status != Purchase.STATUS_PENDING:
        return purchase
    master = purchase.master
    field = 'promoted_until' if purchase.kind == KIND_TOP else 'pro_until'
    now = timezone.now()
    start = max(getattr(master, field) or now, now)
    setattr(master, field, start + timedelta(days=purchase.days))
    master.save(update_fields=[field])
    purchase.status = Purchase.STATUS_PAID
    purchase.paid_at = now
    purchase.save(update_fields=['status', 'paid_at'])
    return purchase


def fee_percent_for(master):
    """Platforma komissiyasi: PRO ustalar uchun pasaytirilgan."""
    from decimal import Decimal
    if master is not None and master.is_pro:
        return Decimal(str(getattr(settings, 'PRO_FEE_PERCENT', 5)))
    return Decimal(str(getattr(settings, 'PLATFORM_FEE_PERCENT', 10)))


def active_orders_limit(master):
    """Usta bir vaqtda nechta faol buyurtma ushlab tura oladi (lentadan olishda tekshiriladi)."""
    return getattr(settings, 'PRO_ACTIVE_ORDERS_LIMIT', 10) if master.is_pro else getattr(
        settings, 'ACTIVE_ORDERS_LIMIT', 5)
