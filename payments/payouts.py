"""Ustalarga pul o'tkazish: hisobot, haftalik jadval va qayd.

Eskroudan chiqarilgan (released) bosqichlar ustaga tegishli, lekin pul hali platforma
hisobida. Administrator:
  1) "To'lanishi kerak" ro'yxatini ochadi yoki Excel'ga yuklaydi;
  2) bank/to'lov tizimi orqali ustalarning kartasiga o'tkazadi;
  3) o'tkazilganlarni belgilaydi — har bir usta uchun Payout yozuvi yaratiladi.

Haftalik jadval (prepare_weekly, cron): PAYOUT_WEEKDAY kuni kartasi bor va summasi PAYOUT_MIN_AMOUNT
dan kam bo'lmagan ustalar uchun o'tkazma tayyorlanadi (chiqarilganiga PAYOUT_DELAY_HOURS bo'lgan
bosqichlar), provayderga yuboriladi (payout_providers.py) va administratorga xabar beriladi.
O'tkazildi deb belgilanganda usta SMS/Telegram/bildirishnoma oladi.
"""

from datetime import timedelta

from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Milestone, Payout


def _pending_milestones():
    return (Milestone.objects.filter(state=Milestone.STATE_RELEASED, paid_out_at__isnull=True,
                                     payout__isnull=True, order__master__isnull=False)
            .select_related('order', 'order__master').order_by('order__master__full_name', 'released_at'))


def pending():
    """Har bir usta uchun: to'lanishi kerak bo'lgan bosqichlar va summalar."""
    rows = {}
    for m in _pending_milestones():
        master = m.order.master
        row = rows.setdefault(master.pk, {'master': master, 'milestones': [], 'gross': 0, 'fee': 0, 'amount': 0,
                                          'oldest': m.released_at})
        row['milestones'].append(m)
        row['gross'] += m.amount_due   # mijoz haqiqatan to'lagan (promo-kod chegirmasi ayirilgan)
        row['fee'] += m.fee_amount
        row['amount'] += m.master_amount
        if m.released_at and (row['oldest'] is None or m.released_at < row['oldest']):
            row['oldest'] = m.released_at
    result = list(rows.values())
    for row in result:
        row['count'] = len(row['milestones'])
        row['has_card'] = bool(row['master'].payout_card)
    return result


def totals(rows):
    return {key: sum((r[key] for r in rows), 0) for key in ('gross', 'fee', 'amount', 'count')}


@transaction.atomic
def mark_paid(master_ids, user=None, note=''):
    """Tanlangan ustalarning barcha kutayotgan bosqichlarini "o'tkazildi" deb belgilaydi."""
    created = []
    now = timezone.now()
    locked = (Milestone.objects.select_for_update(of=('self',))
              .filter(state=Milestone.STATE_RELEASED, paid_out_at__isnull=True, payout__isnull=True,
                      order__master_id__in=master_ids)
              .select_related('order', 'order__master'))
    by_master = {}
    for m in locked:
        by_master.setdefault(m.order.master, []).append(m)
    for master, items in by_master.items():
        payout = Payout.objects.create(
            master=master, count=len(items),
            gross=sum((m.amount_due for m in items), 0), fee=sum((m.fee_amount for m in items), 0),
            amount=sum((m.master_amount for m in items), 0),
            card=master.payout_card, holder=master.payout_holder, note=note[:255], created_at=now,
            created_by=user if getattr(user, 'pk', None) else None, status=Payout.STATUS_PAID, paid_at=now,
        )
        Milestone.objects.filter(pk__in=[m.pk for m in items]).update(paid_out_at=now, payout=payout)
        created.append(payout)
        transaction.on_commit(lambda p=payout: notify_master(p))
    return created


# ---------- Haftalik jadval ----------

def next_payout_date(now=None):
    today = timezone.localdate(now)
    days = (settings.PAYOUT_WEEKDAY - today.weekday()) % 7
    return today + timedelta(days=days)


@transaction.atomic
def prepare_weekly(now=None, force=False):
    """To'lov kuni: tayyorlangan o'tkazmalar ro'yxati. Kunda bir marta (force — admin qo'lda chaqirganda)."""
    from .payout_providers import get_provider
    now = now or timezone.now()
    today = timezone.localdate(now)
    if not force and (today.weekday() != settings.PAYOUT_WEEKDAY
                      or Payout.objects.filter(provider__isnull=False, created_at__date=today,
                                               note__startswith='Haftalik').exists()):
        return []
    cutoff = now - timedelta(hours=settings.PAYOUT_DELAY_HOURS)
    provider = get_provider()
    created = []
    for row in pending():
        master = row['master']
        items = [m for m in row['milestones'] if m.released_at and m.released_at <= cutoff]
        amount = sum((m.master_amount for m in items), 0)
        if not master.payout_card or not items or amount < settings.PAYOUT_MIN_AMOUNT:
            continue   # karta yo'q yoki summa kichik — keyingi haftaga o'tadi
        payout = Payout.objects.create(
            master=master, count=len(items), gross=sum((m.amount_due for m in items), 0),
            fee=sum((m.fee_amount for m in items), 0), amount=amount, card=master.payout_card,
            holder=master.payout_holder, note=f'Haftalik {today:%d.%m.%Y}', created_at=now,
            status=Payout.STATUS_PREPARED, provider=provider.name)
        # Qulf + shart: shu orada admin qo'lda to'lab qo'ygan bosqich ikkinchi marta o'tkazilmasin
        ids = list(Milestone.objects.select_for_update().filter(
            pk__in=[m.pk for m in items], payout__isnull=True, paid_out_at__isnull=True,
            state=Milestone.STATE_RELEASED).values_list('pk', flat=True))
        if len(ids) != len(items):
            payout.delete()
            continue
        Milestone.objects.filter(pk__in=ids).update(payout=payout)
        status, ref, error = provider.send(payout)
        if status == Payout.STATUS_PAID:
            confirm(payout, ref=ref)
        elif status == Payout.STATUS_FAILED:
            Payout.objects.filter(pk=payout.pk).update(status=Payout.STATUS_FAILED, note=(payout.note + ' ' + error)[:255])
            Milestone.objects.filter(payout=payout).update(payout=None)   # keyingi safar qayta urinish
        created.append(payout)
    if created:
        transaction.on_commit(lambda: _notify_admin(created))
    return created


@transaction.atomic
def confirm(payout, user=None, ref=''):
    """Tayyorlangan o'tkazma ustaga o'tkazildi."""
    payout = Payout.objects.select_for_update().get(pk=payout.pk)
    if payout.status == Payout.STATUS_PAID:
        return payout
    now = timezone.now()
    payout.status, payout.paid_at, payout.provider_ref = Payout.STATUS_PAID, now, ref or payout.provider_ref
    if user is not None and getattr(user, 'pk', None):
        payout.created_by = user
    payout.save(update_fields=['status', 'paid_at', 'provider_ref', 'created_by'])
    payout.milestones.update(paid_out_at=now)
    transaction.on_commit(lambda: notify_master(payout))
    return payout


@transaction.atomic
def cancel_prepared(payout):
    """Tayyorlangan o'tkazmani bekor qilish — bosqichlar yana «to'lanishi kerak» ro'yxatiga qaytadi."""
    payout = Payout.objects.select_for_update().get(pk=payout.pk)
    if payout.status == Payout.STATUS_PAID:
        return False
    payout.milestones.update(payout=None)
    payout.delete()
    return True


def notify_master(payout):
    from repair_service import webpush
    master = payout.master
    with translation.override(settings.LANGUAGE_CODE):
        text = _("%(amount)s so'm kartangizga (•••• %(card)s) o'tkazildi. Rahmat!") % {
            'amount': f'{int(payout.amount):,}'.replace(',', ' '), 'card': (payout.card or '')[-4:]}
    webpush.notify(master.push_subscriptions.all(), settings.SITE_INFO['name'], text, '/kabinet/')
    if master.telegram_chat_id:
        from telegram_bot import client
        client.send_message(master.telegram_chat_id, text)
    else:
        from otp.sms import send_sms
        send_sms(master.phone, text, background=True)


def _notify_admin(payouts_list):
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not chat_id:
        return
    from django.urls import reverse

    from telegram_bot import client
    total = sum((p.amount for p in payouts_list), 0)
    url = settings.SITE_URL.rstrip('/') + reverse('admin:payments_payout_changelist') + '?status__exact=prepared'
    client.send_message(chat_id, f"💸 Haftalik to'lov ro'yxati tayyor: {len(payouts_list)} usta, "
                                 f"{int(total):,} so'm.\n{url}".replace(',', ' '))


def card_display(card):
    return ' '.join(card[i:i + 4] for i in range(0, len(card), 4)) if card else ''


# ---------- Excel ----------

def _workbook(title, header, rows, widths):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    book = Workbook()
    sheet = book.active
    sheet.title = title
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for index, width in enumerate(widths):
        sheet.column_dimensions[chr(ord('A') + index)].width = width
    sheet.freeze_panes = 'A2'
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _text(value):
    """Karta/telefon raqami Excel'da son bo'lib buzilmasligi va formula sifatida
    bajarilmasligi uchun (=, +, -, @ bilan boshlanuvchi matn)."""
    value = str(value or '')
    return "'" + value if value[:1] in ('=', '+', '-', '@', '\t', '\r', '|', '%') else value


def pending_xlsx(rows=None):
    rows = pending() if rows is None else rows
    data = [[_text(r['master'].full_name), _text(r['master'].phone), card_display(r['master'].payout_card),
             _text(r['master'].payout_holder), r['count'], int(r['gross']), int(r['fee']), int(r['amount']),
             ', '.join(f'#{m.order_id}' for m in r['milestones'])] for r in rows]
    total = totals(rows)
    data.append(['JAMI', '', '', '', total['count'], int(total['gross']), int(total['fee']), int(total['amount']), ''])
    return _workbook("To'lanishi kerak",
                     ['Usta', 'Telefon', 'Karta', 'Karta egasi', 'Bosqichlar', "Mijozlar to'lagan", 'Komissiya',
                      "O'tkaziladigan summa", 'Buyurtmalar'], data, [28, 16, 22, 26, 11, 18, 14, 22, 30])


def history_xlsx(queryset):
    data = [[timezone.localtime(p.created_at).strftime('%d.%m.%Y %H:%M'), _text(p.master.full_name),
             _text(p.master.phone), card_display(p.card), _text(p.holder), p.count, int(p.gross), int(p.fee),
             int(p.amount), _text(p.note)] for p in queryset.select_related('master')]
    return _workbook("O'tkazmalar",
                     ['Sana', 'Usta', 'Telefon', 'Karta', 'Karta egasi', 'Bosqichlar', "Mijozlar to'lagan",
                      'Komissiya', "O'tkazilgan", 'Izoh'], data, [18, 28, 16, 22, 26, 11, 18, 14, 16, 30])
