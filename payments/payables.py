"""To'lov tizimlari uchun yagona interfeys: "to'lanadigan narsa".

Payme/Click/Uzum bizga hisob raqami (account) sifatida kalit yuboradi:
    "15"   — buyurtma bosqichi (Milestone #15)
    "p7"   — tarif xaridi (Purchase #7)
Har bir provayder kodi faqat shu interfeys bilan ishlaydi va nima sotilayotganini bilmaydi.
"""

from . import services, tariffs
from .models import Milestone, Payment, Purchase


class MilestonePayable:
    def __init__(self, milestone):
        self.obj = milestone
        self.key = str(milestone.pk)
        self.amount = milestone.amount
        self.fk = {'milestone': milestone}

    @property
    def is_pending(self):
        return self.obj.state == Milestone.STATE_PENDING

    def mark_paid(self):
        services.mark_held(self.obj)

    @property
    def cancel_locked(self):
        """To'lovdan keyin bekor qilib bo'lmaydi: pul allaqachon ustaga chiqarilgan."""
        self.obj.refresh_from_db()
        return self.obj.state == Milestone.STATE_RELEASED

    def cancel_paid(self):
        if self.obj.state == Milestone.STATE_HELD:
            services.refund(self.obj)

    def return_path(self):
        return self.obj.order.get_customer_url()


class PurchasePayable:
    def __init__(self, purchase):
        self.obj = purchase
        self.key = f'p{purchase.pk}'
        self.amount = purchase.amount
        self.fk = {'purchase': purchase}

    @property
    def is_pending(self):
        return self.obj.status == Purchase.STATUS_PENDING

    def mark_paid(self):
        tariffs.activate(self.obj)

    @property
    def cancel_locked(self):
        """Tarif faollashgan — xizmat ko'rsatilgan, to'lov tizimi orqali bekor qilinmaydi."""
        self.obj.refresh_from_db()
        return self.obj.status == Purchase.STATUS_PAID

    def cancel_paid(self):
        pass

    def return_path(self):
        from django.urls import reverse
        return reverse('payments:tariffs')


def wrap(obj):
    return PurchasePayable(obj) if isinstance(obj, Purchase) else MilestonePayable(obj)


def resolve(key, lock=False):
    """Hisob kaliti bo'yicha payable. Topilmasa None."""
    key = str(key or '').strip()
    try:
        if key.startswith('p'):
            qs = Purchase.objects.select_related('master')
            return PurchasePayable((qs.select_for_update() if lock else qs).get(pk=int(key[1:])))
        qs = Milestone.objects.select_related('order')
        return MilestonePayable((qs.select_for_update() if lock else qs).get(pk=int(key)))
    except (ValueError, Milestone.DoesNotExist, Purchase.DoesNotExist):
        return None


def for_payment(payment):
    return wrap(payment.purchase if payment.purchase_id else payment.milestone)


def account_key(payment):
    return f'p{payment.purchase_id}' if payment.purchase_id else str(payment.milestone_id)


def open_payments(payable, provider):
    return Payment.objects.filter(provider=provider, state=Payment.STATE_CREATED, **payable.fk)
