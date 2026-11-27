"""Nizolarni hal qilish (administrator).

Mijoz «Muammo bor» deganda buyurtma «Nizo» holatiga o'tadi va ushlab turilgan pul muzlaydi.
Administrator ikkala tomonni eshitib (yozishma, rasmlar, tarix — bitta sahifada) qaror qiladi:

- resolve(order, released_ids, note) — har bir ushlab turilgan bosqich bo'yicha: ustaga chiqarish
  yoki mijozga qaytarish. Biror qism ustaga chiqarilsa — buyurtma «Tasdiqlandi», hammasi
  qaytarilsa — «Bekor qilindi». Qaytarilgan pulni to'lov tizimi kabinetidan qaytarish kerak.
- withdraw(order, note) — kelishildi, ish davom etadi: buyurtma nizodan oldingi holatiga qaytadi.
"""

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.html import escape
from django.utils.translation import gettext as _

from payments.models import Milestone

from .models import OrderEvent, ServiceRequest as SR


class DisputeError(Exception):
    pass


def opened_event(order):
    return order.events.filter(status=SR.STATUS_DISPUTED).order_by('-created_at').first()


def status_before(order):
    """Nizodan oldingi holat (withdraw uchun)."""
    event = opened_event(order)
    if event is None:
        return SR.STATUS_COMPLETED
    previous = (order.events.filter(created_at__lte=event.created_at).exclude(status=SR.STATUS_DISPUTED)
                .exclude(pk=event.pk).order_by('-created_at', '-pk').first())
    return previous.status if previous and previous.status in SR.FLOW else SR.STATUS_COMPLETED


def open_disputes():
    orders = list(SR.objects.filter(status=SR.STATUS_DISPUTED).select_related('master', 'category')
                  .order_by('updated_at'))
    now = timezone.now()
    for order in orders:
        event = opened_event(order)
        order.dispute_opened_at = event.created_at if event else order.updated_at
        order.dispute_reason = event.note if event else ''
        order.dispute_days = (now - order.dispute_opened_at).days
        order.held_total = sum((m.amount for m in order.milestones.filter(state=Milestone.STATE_HELD)), 0)
    return orders


@transaction.atomic
def resolve(order, released_ids, note, outcome=None):
    """outcome ('master'/'customer') — ushlab turilgan mablag' bo'lmasa (masalan naqd reja), kim haqligini admin aytadi."""
    note = (note or '').strip()
    if not note:
        raise DisputeError("Qaror izohini yozing — ikkala tomon uni ko'radi.")
    order = SR.objects.select_for_update().get(pk=order.pk)
    if order.status != SR.STATUS_DISPUTED:
        raise DisputeError('Buyurtma nizo holatida emas.')
    released_ids = {int(i) for i in released_ids}
    now = timezone.now()
    released = refunded = 0
    held = list(order.milestones.select_for_update().filter(state=Milestone.STATE_HELD))
    if not held and outcome not in ('master', 'customer'):
        raise DisputeError("Ushlab turilgan mablag' yo'q — qaror kimning foydasiga ekanini tanlang.")
    for milestone in held:
        if milestone.pk in released_ids:
            milestone.state, milestone.released_at = Milestone.STATE_RELEASED, now
            released += milestone.amount
        else:
            milestone.state, milestone.refunded_at = Milestone.STATE_REFUNDED, now
            refunded += milestone.amount_due   # mijoz haqiqatan to'lagan summa
            from payments.refunds import request_refund
            transaction.on_commit(lambda m=milestone: request_refund(m, note=f'Nizo #{order.pk}'))
        milestone.save(update_fields=['state', 'released_at', 'refunded_at'])
    if held:
        any_released = released or order.milestones.filter(state=Milestone.STATE_RELEASED).exists()
        order.status = SR.STATUS_CONFIRMED if any_released or not refunded else SR.STATUS_CANCELLED
    else:
        order.status = SR.STATUS_CONFIRMED if outcome == 'master' else SR.STATUS_CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    summary = _("Nizo hal qilindi: ustaga %(r)s so'm, mijozga %(f)s so'm. %(note)s") % {
        'r': _money(released), 'f': _money(refunded), 'note': note}
    OrderEvent.objects.create(order=order, status=order.status, actor=OrderEvent.ACTOR_ADMIN, note=summary[:500])
    transaction.on_commit(lambda: _notify(order, note, released, refunded))
    if order.status == SR.STATUS_CONFIRMED:
        from payments.promos import on_confirmed
        transaction.on_commit(lambda: on_confirmed(order))
    return {'released': released, 'refunded': refunded, 'status': order.status}


@transaction.atomic
def withdraw(order, note):
    note = (note or '').strip()
    if not note:
        raise DisputeError("Izoh yozing — ikkala tomon uni ko'radi.")
    order = SR.objects.select_for_update().get(pk=order.pk)
    if order.status != SR.STATUS_DISPUTED:
        raise DisputeError('Buyurtma nizo holatida emas.')
    order.status = status_before(order)
    order.save(update_fields=['status', 'updated_at'])
    OrderEvent.objects.create(order=order, status=order.status, actor=OrderEvent.ACTOR_ADMIN,
                              note=(_('Nizo yopildi, ish davom etadi. %(note)s') % {'note': note})[:500])
    transaction.on_commit(lambda: _notify(order, note, None, None))
    return order


def _money(value):
    return f'{int(value):,}'.replace(',', ' ')


def _notify(order, note, released, refunded):
    from . import customer_notify
    order = SR.objects.select_related('master').get(pk=order.pk)
    with translation.override(order.language or 'uz'):
        if released is None:
            text = _("Nizo yopildi, ish davom etadi. Administrator: %(note)s %(url)s")
        elif refunded:
            text = _("Nizo hal qilindi: %(amount)s so'm sizga qaytariladi. Administrator: %(note)s %(url)s")
        else:
            text = _("Nizo hal qilindi. Administrator: %(note)s %(url)s")
        customer_notify._to_customer(order, text % {'note': note, 'amount': _money(refunded or 0),
                                                    'url': customer_notify._customer_link(order)})
    if order.master:
        with translation.override(settings.LANGUAGE_CODE):
            text = (_("#%(id)s bo'yicha nizo yopildi, ishni davom ettiring. Administrator: %(note)s")
                    if released is None else
                    _("#%(id)s bo'yicha nizo hal qilindi: sizga %(amount)s so'm. Administrator: %(note)s"))
            customer_notify._to_master(order, text % {'id': order.pk, 'note': note, 'amount': _money(released or 0)})


def notify_admin_opened(order, reason=''):
    """Nizo ochilganda administrator chatiga Telegram xabari."""
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not chat_id:
        return
    from django.urls import reverse

    from telegram_bot import client
    url = settings.SITE_URL.rstrip('/') + reverse('admin_dispute', args=[order.pk])
    client.send_message(chat_id, f'⚠️ Nizo: buyurtma #{order.pk}\n{escape(reason[:300])}\n{url}')
