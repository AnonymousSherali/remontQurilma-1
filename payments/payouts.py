"""Ustalarga pul o'tkazish hisoboti.

Eskroudan chiqarilgan (released) bosqichlar ustaga tegishli, lekin pul hali platforma
hisobida. Administrator:
  1) "To'lanishi kerak" ro'yxatini ochadi yoki Excel'ga yuklaydi;
  2) bank/to'lov tizimi orqali ustalarning kartasiga o'tkazadi;
  3) o'tkazilganlarni belgilaydi — har bir usta uchun Payout yozuvi yaratiladi.
"""

from io import BytesIO

from django.db import transaction
from django.utils import timezone

from .models import Milestone, Payout


def _pending_milestones():
    return (Milestone.objects.filter(state=Milestone.STATE_RELEASED, paid_out_at__isnull=True,
                                     order__master__isnull=False)
            .select_related('order', 'order__master').order_by('order__master__full_name', 'released_at'))


def pending():
    """Har bir usta uchun: to'lanishi kerak bo'lgan bosqichlar va summalar."""
    rows = {}
    for m in _pending_milestones():
        master = m.order.master
        row = rows.setdefault(master.pk, {'master': master, 'milestones': [], 'gross': 0, 'fee': 0, 'amount': 0,
                                          'oldest': m.released_at})
        row['milestones'].append(m)
        row['gross'] += m.amount
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
    locked = (Milestone.objects.select_for_update()
              .filter(state=Milestone.STATE_RELEASED, paid_out_at__isnull=True, order__master_id__in=master_ids)
              .select_related('order', 'order__master'))
    by_master = {}
    for m in locked:
        by_master.setdefault(m.order.master, []).append(m)
    for master, items in by_master.items():
        payout = Payout.objects.create(
            master=master, count=len(items),
            gross=sum((m.amount for m in items), 0), fee=sum((m.fee_amount for m in items), 0),
            amount=sum((m.master_amount for m in items), 0),
            card=master.payout_card, holder=master.payout_holder, note=note[:255], created_at=now,
            created_by=user if getattr(user, 'pk', None) else None,
        )
        Milestone.objects.filter(pk__in=[m.pk for m in items]).update(paid_out_at=now, payout=payout)
        created.append(payout)
    return created


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
    return "'" + value if value[:1] in ('=', '+', '-', '@') else value


def pending_xlsx(rows=None):
    rows = pending() if rows is None else rows
    data = [[r['master'].full_name, _text(r['master'].phone), card_display(r['master'].payout_card),
             _text(r['master'].payout_holder), r['count'], int(r['gross']), int(r['fee']), int(r['amount']),
             ', '.join(f'#{m.order_id}' for m in r['milestones'])] for r in rows]
    total = totals(rows)
    data.append(['JAMI', '', '', '', total['count'], int(total['gross']), int(total['fee']), int(total['amount']), ''])
    return _workbook("To'lanishi kerak",
                     ['Usta', 'Telefon', 'Karta', 'Karta egasi', 'Bosqichlar', "Mijozlar to'lagan", 'Komissiya',
                      "O'tkaziladigan summa", 'Buyurtmalar'], data, [28, 16, 22, 26, 11, 18, 14, 22, 30])


def history_xlsx(queryset):
    data = [[timezone.localtime(p.created_at).strftime('%d.%m.%Y %H:%M'), p.master.full_name,
             _text(p.master.phone), card_display(p.card), _text(p.holder), p.count, int(p.gross), int(p.fee),
             int(p.amount), _text(p.note)] for p in queryset.select_related('master')]
    return _workbook("O'tkazmalar",
                     ['Sana', 'Usta', 'Telefon', 'Karta', 'Karta egasi', 'Bosqichlar', "Mijozlar to'lagan",
                      'Komissiya', "O'tkazilgan", 'Izoh'], data, [18, 28, 16, 22, 26, 11, 18, 14, 16, 30])
