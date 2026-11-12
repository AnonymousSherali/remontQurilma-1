"""Kelish vaqti.

Mijoz arizada qulay kun va oraliqni aytadi (ixtiyoriy). Usta buyurtmani qabul qilgach
aniq vaqtni belgilaydi — mijoz xabar oladi, ustaning kabinetida taqvim paydo bo'ladi.
Vaqtdan VISIT_REMINDER_HOURS soat oldin ikkala tomonga eslatma boradi (process_orders).
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from .models import OrderEvent, ServiceRequest as SR

MAX_DAYS_AHEAD = 30
# Usta shu holatlarda vaqtni belgilaydi/o'zgartiradi (joyga kelgach — ma'nosi yo'q)
SETTABLE = (SR.STATUS_ACCEPTED,)


class ScheduleError(Exception):
    pass


def preferred_label(order):
    """"Ertaga, 14-noyabr · Kechqurun 16:00–20:00" yoki bo'sh satr."""
    parts = []
    if order.preferred_date:
        parts.append(date_format(order.preferred_date, 'j-F'))
    if order.preferred_slot:
        parts.append(str(order.get_preferred_slot_display()))
    return ' · '.join(parts)


def date_choices(days=7):
    """Ariza formasidagi kun tanlovi: bugundan boshlab bir hafta."""
    today = timezone.localdate()
    names = {0: _('Bugun'), 1: _('Ertaga')}
    return [(d.isoformat(), names.get(i) or date_format(d, 'D, j-M'))
            for i, d in ((i, today + timedelta(days=i)) for i in range(days))]


def can_set(order):
    return order.master_id is not None and order.status in SETTABLE


def parse(date_text, time_text):
    try:
        naive = datetime.strptime(f'{date_text} {time_text}', '%Y-%m-%d %H:%M')
    except (TypeError, ValueError):
        raise ScheduleError(_("Sana va vaqtni to'g'ri kiriting."))
    return timezone.make_aware(naive, timezone.get_current_timezone())


def conflicts(order, when, window=timedelta(minutes=59)):
    """Shu ustaning yaqin vaqtga belgilangan boshqa tashriflari (ogohlantirish uchun)."""
    return list(SR.objects.filter(
        master_id=order.master_id, visit_at__range=(when - window, when + window),
        status__in=(SR.STATUS_ACCEPTED, SR.STATUS_ARRIVED, SR.STATUS_IN_PROGRESS),
    ).exclude(pk=order.pk))


def _visit_text(order):
    return date_format(timezone.localtime(order.visit_at), 'j-F, H:i')


@transaction.atomic
def set_visit(order, when, now=None):
    now = now or timezone.now()
    order = SR.objects.select_for_update().select_related('master').get(pk=order.pk)
    if not can_set(order):
        raise ScheduleError(_("Kelish vaqtini hozir o'zgartirib bo'lmaydi."))
    if when < now - timedelta(minutes=5):
        raise ScheduleError(_("O'tib ketgan vaqtni belgilab bo'lmaydi."))
    if when > now + timedelta(days=MAX_DAYS_AHEAD):
        raise ScheduleError(_("Kelish vaqti %(n)s kundan uzoq bo'lmasligi kerak.") % {'n': MAX_DAYS_AHEAD})
    changed = order.visit_at is not None
    order.visit_at = when
    order.visit_reminded = False
    order.save(update_fields=['visit_at', 'visit_reminded', 'updated_at'])
    with translation.override(order.language or 'uz'):
        note = (_("Kelish vaqti o'zgartirildi: %(t)s") if changed else _('Kelish vaqti: %(t)s')) % {
            't': _visit_text(order)}
    OrderEvent.objects.create(order=order, status=order.status, actor=OrderEvent.ACTOR_MASTER, note=note)
    transaction.on_commit(lambda: _notify_customer(order, changed))
    return order


def _notify_customer(order, changed=False):
    from . import customer_notify
    with translation.override(order.language or 'uz'):
        text = (_("Usta kelish vaqtini o'zgartirdi: %(t)s. %(url)s") if changed
                else _('Usta %(t)s da keladi. %(url)s'))
        customer_notify._to_customer(order, text % {
            't': _visit_text(order), 'url': customer_notify._customer_link(order)})


def send_reminders(now=None):
    """Tashrifga oz qolganda ikkala tomonga bir martalik eslatma."""
    from . import customer_notify
    now = now or timezone.now()
    soon = now + timedelta(hours=settings.VISIT_REMINDER_HOURS)
    sent = []
    orders = SR.objects.select_related('master', 'category').filter(
        status=SR.STATUS_ACCEPTED, visit_reminded=False, visit_at__gt=now, visit_at__lte=soon,
        master__isnull=False)
    for order in orders:
        if not SR.objects.filter(pk=order.pk, visit_reminded=False).update(visit_reminded=True):
            continue
        with translation.override(order.language or 'uz'):
            customer_notify._to_customer(order, _('Eslatma: usta bugun %(t)s da keladi. %(url)s') % {
                't': date_format(timezone.localtime(order.visit_at), 'H:i'),
                'url': customer_notify._customer_link(order)})
        with translation.override(settings.LANGUAGE_CODE):
            customer_notify._to_master(order, _('Eslatma: #%(id)s buyurtma — %(t)s da. %(url)s') % {
                'id': order.pk, 't': date_format(timezone.localtime(order.visit_at), 'H:i'),
                'url': customer_notify._absolute(order.get_master_url())})
        sent.append(order)
    return sent


def calendar(master, now=None):
    """Usta kabineti uchun: kelgusi tashriflar kunlar bo'yicha + vaqti belgilanmagan buyurtmalar."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    active = (SR.STATUS_ACCEPTED, SR.STATUS_ARRIVED, SR.STATUS_IN_PROGRESS)
    orders = list(master.requests.filter(status__in=active).select_related('category').order_by('visit_at'))
    days = {}
    for order in orders:
        if order.visit_at is None:
            continue
        local = timezone.localtime(order.visit_at)
        order.visit_local = local
        order.visit_overdue = order.status == SR.STATUS_ACCEPTED and order.visit_at < now
        days.setdefault(local.date(), []).append(order)
    names = {0: _('Bugun'), 1: _('Ertaga')}
    return {
        'days': [{'date': d, 'label': names.get((d - today).days) or date_format(d, 'l, j-F'), 'orders': items}
                 for d, items in sorted(days.items())],
        'unscheduled': [o for o in orders if o.visit_at is None and o.status == SR.STATUS_ACCEPTED],
    }
