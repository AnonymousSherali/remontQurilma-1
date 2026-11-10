"""Kafolat: tasdiqlangan ish kafolat muddati ichida yana buzilsa.

Oqim:
  mijoz murojaat qiladi (open) -> usta bepul tuzatadi (fixed) -> mijoz tasdiqlaydi (resolved)
  Mijoz natijadan norozi bo'lsa yoki usta WARRANTY_RESPONSE_HOURS ichida javob bermasa —
  administratorga o'tkazadi (escalated). Administrator rad etadi (rejected) yoki
  kompensatsiya belgilaydi (compensated).

Qoidalar:
- kafolat buyurtma tasdiqlangan kundan boshlanadi; muddati — katalogdagi xizmatda
  ko'rsatilgan kun yoki WARRANTY_DAYS;
- bitta buyurtmada bir vaqtda bitta faol murojaat;
- pul kompensatsiyasi faqat platforma orqali to'langan buyurtmalarga, to'langan summadan
  va GUARANTEE_MAX_AMOUNT dan oshmaydi. Naqd to'langan ishda platforma pulni ko'rmagan —
  faqat ustani qayta yuborish mumkin;
- "usta tuzatdi" holatida mijoz WARRANTY_AUTO_CLOSE_DAYS kun javob bermasa — murojaat yopiladi.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import OrderEvent, ServiceRequest as SR, WarrantyClaim


class WarrantyError(Exception):
    pass


def days_for(order):
    item = order.catalog_item if order.catalog_item_id else None
    if item is not None and item.warranty_days is not None:
        return item.warranty_days
    return settings.WARRANTY_DAYS


def period(order):
    """(boshlanishi, tugashi) yoki None — buyurtma tasdiqlanmagan yoki kafolatsiz."""
    if order.status != SR.STATUS_CONFIRMED or order.master_id is None:
        return None
    days = days_for(order)
    if not days:
        return None
    start = (order.events.filter(status=SR.STATUS_CONFIRMED).order_by('-created_at')
             .values_list('created_at', flat=True).first()) or order.updated_at
    return start, start + timedelta(days=days)


def is_active(order, now=None):
    span = period(order)
    return bool(span) and (now or timezone.now()) <= span[1]


def active_claim(order):
    return order.warranty_claims.filter(status__in=WarrantyClaim.ACTIVE_STATUSES).first()


def can_claim(order):
    return is_active(order) and active_claim(order) is None


def paid_online(order):
    """Platforma orqali to'langan (ustaga chiqarilgan) summa."""
    from payments.models import Milestone
    return sum((m.amount for m in order.milestones.filter(state=Milestone.STATE_RELEASED)), 0)


def max_compensation(order):
    return min(paid_online(order), settings.GUARANTEE_MAX_AMOUNT)


def can_escalate(claim, now=None):
    if claim.status == WarrantyClaim.STATUS_FIXED:
        return True
    return (claim.status == WarrantyClaim.STATUS_OPEN
            and (now or timezone.now()) >= claim.created_at + timedelta(hours=settings.WARRANTY_RESPONSE_HOURS))


def _event(order, actor, note):
    OrderEvent.objects.create(order=order, status=order.status, actor=actor, note=note[:500])


def _notify_customer(order, text):
    from . import customer_notify
    with translation.override(order.language or 'uz'):
        customer_notify._to_customer(order, text() % {'id': order.pk, 'url': customer_notify._customer_link(order)})


def _notify_master(order, text):
    from . import customer_notify
    if order.master is None:
        return
    with translation.override(settings.LANGUAGE_CODE):
        customer_notify._to_master(order, text() % {
            'id': order.pk, 'url': customer_notify._absolute(order.get_master_url())})


def _locked(claim):
    return WarrantyClaim.objects.select_for_update().select_related('order', 'order__master').get(pk=claim.pk)


@transaction.atomic
def file_claim(order, description):
    description = (description or '').strip()
    if len(description) < 10:
        raise WarrantyError(_('Muammoni batafsilroq yozing (kamida 10 ta belgi).'))
    order = SR.objects.select_for_update().select_related('master', 'catalog_item').get(pk=order.pk)
    if not is_active(order):
        raise WarrantyError(_('Bu buyurtma uchun kafolat muddati tugagan yoki kafolat berilmagan.'))
    if active_claim(order):
        raise WarrantyError(_("Bu buyurtma bo'yicha kafolat murojaati allaqachon ochilgan."))
    claim = WarrantyClaim.objects.create(order=order, description=description[:2000])
    _event(order, OrderEvent.ACTOR_CUSTOMER, _('Kafolat murojaati ochildi'))
    transaction.on_commit(lambda: _notify_master(order, lambda: _(
        "Kafolat murojaati: #%(id)s buyurtma bo'yicha mijoz muammo bildirdi. Bepul tuzatib bering: %(url)s")))
    return claim


@transaction.atomic
def master_fixed(claim, note=''):
    claim = _locked(claim)
    if claim.status != WarrantyClaim.STATUS_OPEN:
        raise WarrantyError(_("Bu murojaat holatini o'zgartirib bo'lmaydi."))
    claim.status = WarrantyClaim.STATUS_FIXED
    claim.master_note = (note or '').strip()[:1000]
    claim.save(update_fields=['status', 'master_note', 'updated_at'])
    _event(claim.order, OrderEvent.ACTOR_MASTER, _('Kafolat: usta muammoni tuzatdi'))
    transaction.on_commit(lambda: _notify_customer(claim.order, lambda: _(
        "Usta kafolat bo'yicha muammoni tuzatganini bildirdi. Tekshirib tasdiqlang: %(url)s")))
    return claim


def _close(claim, status, actor, note):
    claim.status = status
    claim.closed_at = timezone.now()
    claim.save()
    _event(claim.order, actor, note)


@transaction.atomic
def customer_resolve(claim):
    claim = _locked(claim)
    if claim.status not in (WarrantyClaim.STATUS_OPEN, WarrantyClaim.STATUS_FIXED):
        raise WarrantyError(_("Bu murojaat holatini o'zgartirib bo'lmaydi."))
    _close(claim, WarrantyClaim.STATUS_RESOLVED, OrderEvent.ACTOR_CUSTOMER, _("Kafolat: muammo hal bo'ldi"))
    transaction.on_commit(lambda: _notify_master(claim.order, lambda: _(
        "Mijoz #%(id)s buyurtma bo'yicha kafolat murojaatini yopdi. Rahmat!")))
    return claim


@transaction.atomic
def customer_escalate(claim):
    claim = _locked(claim)
    if not can_escalate(claim):
        raise WarrantyError(_("Avval ustaga tuzatish uchun vaqt bering — javob bo'lmasa, administratorga "
                              "o'tkazishingiz mumkin."))
    claim.status = WarrantyClaim.STATUS_ESCALATED
    claim.save(update_fields=['status', 'updated_at'])
    _event(claim.order, OrderEvent.ACTOR_CUSTOMER, _("Kafolat: administratorga o'tkazildi"))
    transaction.on_commit(lambda: _notify_master(claim.order, lambda: _(
        "#%(id)s buyurtma bo'yicha kafolat murojaati administratorga o'tkazildi.")))
    return claim


@transaction.atomic
def admin_decide(claim, status, resolution='', compensation=None):
    """Administrator qarori: rejected / compensated / resolved."""
    claim = _locked(claim)
    if not claim.is_active:
        raise WarrantyError('Murojaat allaqachon yopilgan.')
    if status == WarrantyClaim.STATUS_COMPENSATED:
        limit = max_compensation(claim.order)
        if not compensation or compensation <= 0:
            raise WarrantyError('Kompensatsiya summasini kiriting.')
        if compensation > limit:
            raise WarrantyError(
                f"Kompensatsiya {limit:,.0f} so'mdan oshmasligi kerak (platforma orqali to'langan summa va "
                f"kafolat chegarasi). Naqd to'langan buyurtmaga pul kompensatsiyasi berilmaydi.".replace(',', ' '))
        claim.compensation = compensation
        text = lambda: _("Kafolat murojaatingiz bo'yicha kompensatsiya belgilandi. Operator siz bilan "  # noqa: E731
                         "bog'lanadi: %(url)s")
    elif status == WarrantyClaim.STATUS_REJECTED:
        if not (resolution or '').strip():
            raise WarrantyError('Rad etish sababini yozing — mijoz uni ko\'radi.')
        text = lambda: _("Kafolat murojaatingiz ko'rib chiqildi. Javob: %(url)s")  # noqa: E731
    elif status == WarrantyClaim.STATUS_RESOLVED:
        text = lambda: _("Kafolat murojaatingiz yopildi: %(url)s")  # noqa: E731
    else:
        raise WarrantyError("Noto'g'ri holat.")
    claim.resolution = (resolution or '').strip()
    _close(claim, status, OrderEvent.ACTOR_ADMIN, f'Kafolat: {claim.get_status_display()}')
    transaction.on_commit(lambda: _notify_customer(claim.order, text))
    return claim


def auto_close(now=None):
    """Usta tuzatgan, mijoz uzoq javob bermagan murojaatlarni yopadi."""
    now = now or timezone.now()
    deadline = now - timedelta(days=settings.WARRANTY_AUTO_CLOSE_DAYS)
    closed = []
    for claim in WarrantyClaim.objects.filter(status=WarrantyClaim.STATUS_FIXED, updated_at__lte=deadline):
        with transaction.atomic():
            claim = _locked(claim)
            if claim.status == WarrantyClaim.STATUS_FIXED:
                _close(claim, WarrantyClaim.STATUS_RESOLVED, OrderEvent.ACTOR_SYSTEM,
                       'Kafolat: mijoz javob bermadi — yopildi')
                closed.append(claim)
    return closed


def context(order, now=None):
    """Buyurtma sahifasi uchun."""
    span = period(order)
    claims = list(order.warranty_claims.all())
    active = next((c for c in claims if c.is_active), None)
    live = bool(span) and (now or timezone.now()) <= span[1]
    return {
        'warranty': {
            'days': days_for(order), 'until': span[1] if span else None, 'live': live,
            'claims': claims, 'active': active,
            'can_claim': live and active is None,
            'can_escalate': bool(active) and can_escalate(active, now),
            'response_hours': settings.WARRANTY_RESPONSE_HOURS,
        } if span or claims else None,
    }
