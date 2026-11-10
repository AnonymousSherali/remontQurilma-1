"""Eskrou mantiqi. Barcha pul harakatlari shu yerdan o'tadi.

Qoidalar (Upwork milestone va YouDo "xavfsiz bitim" tajribasidan):
1. Usta narx va reja taklif qiladi; mijoz tasdiqlagach bosqichlar yaratiladi.
   Tasdiqlangan narxni bir tomonlama o'zgartirib bo'lmaydi.
2. Usta biror bosqichni belgilashdan oldin shu bosqichga tegishli qism to'langan
   (platformada ushlab turilgan) bo'lishi kerak — usta bepul ishlab qolmaydi.
3. Ushlab turilgan pul ustaga faqat bosqichga yetilganda chiqariladi:
   - mijoz tasdiqlasa — darhol;
   - mijoz indamasa — AUTO_RELEASE_HOURS dan keyin avtomatik (mijoz yo'qolib qolsa
     usta jabr ko'rmasligi uchun; Upwork'da bu 14 kun);
   - nizo ochilgan bo'lsa — hech narsa avtomatik chiqmaydi, admin hal qiladi.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from . import tariffs
from .models import Milestone, Quote
from .plans import PLAN_CASH, split_amount


class PaymentError(Exception):
    pass


def _order_model():
    from repair_service.models import ServiceRequest
    return ServiceRequest


def get_quote(order):
    # Har safar bazadan: order.quote keshi tasdiqlashdan keyin eskirib qolishi mumkin
    # (eskirgan "proposed" holat tasdiqlangan narxni o'zgartirishga yo'l ochardi).
    return Quote.objects.filter(order=order).first()


def quote_approved(order):
    quote = get_quote(order)
    return quote is not None and quote.status == Quote.STATUS_APPROVED


# ---------- Narx taklifi ----------

def can_quote(order):
    """Narx ish boshlanguncha kelishiladi; tasdiqlangandan keyin o'zgarmaydi."""
    SR = _order_model()
    quote = get_quote(order)
    return (
        order.master_id is not None
        and order.status in (SR.STATUS_NEW, SR.STATUS_ACCEPTED, SR.STATUS_ARRIVED)
        and not (quote and quote.status == Quote.STATUS_APPROVED)
    )


@transaction.atomic
def propose_quote(order, amount, plan, note=''):
    if not can_quote(order):
        raise PaymentError(_("Narxni hozir o'zgartirib bo'lmaydi"))
    if amount <= 0:
        raise PaymentError(_("Summa musbat bo'lishi kerak"))
    quote, _created = Quote.objects.update_or_create(order=order, defaults={
        'amount': amount, 'plan': plan, 'note': note,
        'status': Quote.STATUS_PROPOSED, 'proposed_at': timezone.now(), 'decided_at': None,
    })
    order.quote = quote
    return quote


@transaction.atomic
def approve_quote(order):
    quote = Quote.objects.select_for_update().get(order=order)
    if quote.status != Quote.STATUS_PROPOSED:
        raise PaymentError(_('Bu taklif allaqachon ko\'rib chiqilgan'))
    quote.status = Quote.STATUS_APPROVED
    quote.decided_at = timezone.now()
    quote.save(update_fields=['status', 'decided_at'])

    order.milestones.filter(state=Milestone.STATE_PENDING).delete()
    fee = tariffs.fee_percent_for(order.master)  # PRO ustalar uchun pasaytirilgan
    for position, (amount, title, release_status) in enumerate(split_amount(quote.amount, quote.plan), start=1):
        Milestone.objects.create(
            order=order, position=position, title=str(title), amount=amount,
            release_status=release_status, fee_percent=fee,
        )
    return quote


def reject_quote(order):
    quote = order.quote
    if quote.status != Quote.STATUS_PROPOSED:
        raise PaymentError(_('Bu taklif allaqachon ko\'rib chiqilgan'))
    quote.status = Quote.STATUS_REJECTED
    quote.decided_at = timezone.now()
    quote.save(update_fields=['status', 'decided_at'])


# ---------- Bosqichlar ----------

def unfunded_for(order, new_status):
    """Shu holatga o'tishdan oldin to'lanishi shart bo'lgan, lekin to'lanmagan bosqichlar."""
    quote = get_quote(order)
    if not quote or quote.status != Quote.STATUS_APPROVED or quote.plan == PLAN_CASH:
        return []
    return list(order.milestones.filter(release_status=new_status, state=Milestone.STATE_PENDING))


@transaction.atomic
def mark_held(milestone):
    milestone = Milestone.objects.select_for_update().get(pk=milestone.pk)
    if milestone.state != Milestone.STATE_PENDING:
        return milestone  # takroriy xabar — idempotent
    milestone.state = Milestone.STATE_HELD
    milestone.held_at = timezone.now()
    milestone.save(update_fields=['state', 'held_at'])
    return milestone


def releasable(milestone):
    order = milestone.order
    SR = _order_model()
    return (
        milestone.state == Milestone.STATE_HELD
        and order.status != SR.STATUS_DISPUTED
        and order.reached(milestone.release_status)
    )


@transaction.atomic
def release(milestone):
    milestone = Milestone.objects.select_for_update().select_related('order').get(pk=milestone.pk)
    if not releasable(milestone):
        raise PaymentError(_("Bu bosqich mablag'ini hozir chiqarib bo'lmaydi"))
    milestone.state = Milestone.STATE_RELEASED
    milestone.released_at = timezone.now()
    milestone.save(update_fields=['state', 'released_at'])
    return milestone


@transaction.atomic
def refund(milestone):
    """Admin nizoni mijoz foydasiga hal qilganda. Pulni to'lov tizimi kabinetidan qaytarish kerak."""
    milestone = Milestone.objects.select_for_update().get(pk=milestone.pk)
    if milestone.state != Milestone.STATE_HELD:
        raise PaymentError(_('Faqat ushlab turilgan mablag\' qaytariladi'))
    milestone.state = Milestone.STATE_REFUNDED
    milestone.refunded_at = timezone.now()
    milestone.save(update_fields=['state', 'refunded_at'])
    return milestone


def release_on_confirm(order):
    """Mijoz buyurtmani tasdiqladi — bosqichi kelgan barcha ushlab turilgan mablag' chiqariladi."""
    released = []
    for milestone in order.milestones.filter(state=Milestone.STATE_HELD):
        if releasable(milestone):
            released.append(release(milestone))
    return released


def auto_release(now=None):
    """Mijoz AUTO_RELEASE_HOURS davomida e'tiroz bildirmagan bosqichlarni chiqaradi (cron)."""
    now = now or timezone.now()
    hours = getattr(settings, 'AUTO_RELEASE_HOURS', 48)
    released = []
    for milestone in Milestone.objects.filter(state=Milestone.STATE_HELD).select_related('order'):
        reached_at = (
            milestone.order.events.filter(status=milestone.release_status).order_by('created_at')
            .values_list('created_at', flat=True).first()
        )
        if reached_at and now - reached_at >= timedelta(hours=hours) and releasable(milestone):
            released.append(release(milestone))
    return released


def summary(order):
    """Sahifalar uchun: jami, to'langan, chiqarilgan, ustaga tegishli."""
    milestones = list(order.milestones.all())
    total = sum((m.amount for m in milestones), 0)
    held = sum((m.amount for m in milestones if m.state == Milestone.STATE_HELD), 0)
    released = sum((m.amount for m in milestones if m.state == Milestone.STATE_RELEASED), 0)
    master_net = sum((m.master_amount for m in milestones if m.state == Milestone.STATE_RELEASED), 0)
    return {'total': total, 'held': held, 'released': released, 'master_net': master_net,
            'paid': held + released, 'milestones': milestones}
