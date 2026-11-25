"""Ustaning ish jadvali: ish kunlari, soatlari va dam olish kunlari.

- Dam olish kunida usta qidiruvda ko'rinmaydi, lentadan buyurtma olmaydi va unga yangi
  buyurtma xabari bormaydi (mavjud buyurtmalari o'zgarmaydi).
- Ish vaqtidan tashqarida usta qidiruvda qoladi, lekin kartochkada «Hozir ishlamaydi — ertaga 08:00 dan»
  ko'rinadi; kelish vaqtini ish vaqtidan tashqariga qo'ysa — ogohlantirish (taqiq emas).
"""

from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

WEEKDAYS = list(range(7))


def weekday_names():
    return [_('Du'), _('Se'), _('Ch'), _('Pa'), _('Ju'), _('Sh'), _('Ya')]


def is_day_off(master, day=None):
    day = day or timezone.localdate()
    return master.days_off.filter(start__lte=day, end__gte=day).exists()


def works_on(master, day):
    return (not master.work_days or day.weekday() in master.work_days) and not is_day_off(master, day)


def is_working(master, moment=None):
    """Hozir (yoki berilgan vaqtda) ish vaqtimi."""
    moment = timezone.localtime(moment or timezone.now())
    if not works_on(master, moment.date()):
        return False
    if master.work_from and master.work_to:
        return master.work_from <= moment.time() < master.work_to
    return True


def next_working_start(master, moment=None, horizon=30):
    """Keyingi ish boshlanishi (lokal datetime) yoki None."""
    moment = timezone.localtime(moment or timezone.now())
    start_time = master.work_from or time(0, 0)
    for offset in range(horizon):
        day = moment.date() + timedelta(days=offset)
        if not works_on(master, day):
            continue
        start = timezone.make_aware(datetime.combine(day, start_time))
        if offset == 0 and master.work_to and moment.time() >= master.work_to:
            continue
        return max(start, moment) if offset == 0 else start
    return None


def summary(master):
    """«Du–Ju, 08:00–20:00» ko'rinishida. Jadval kiritilmagan bo'lsa — bo'sh satr."""
    if not master.work_days and not master.work_from:
        return ''
    names = weekday_names()
    days = sorted(master.work_days) if master.work_days else WEEKDAYS
    if len(days) == 7:
        day_text = _('Har kuni')
    elif days == list(range(days[0], days[-1] + 1)) and len(days) > 2:
        day_text = f'{names[days[0]]}–{names[days[-1]]}'
    else:
        day_text = ', '.join(names[d] for d in days)
    hours = f" {master.work_from:%H:%M}–{master.work_to:%H:%M}" if master.work_from and master.work_to else ''
    return day_text + hours


def status_label(master, moment=None):
    """Kartochka uchun: '' (ishlayapti) yoki «Dam olishda» / «Hozir ishlamaydi — ertaga 08:00 dan»."""
    moment = timezone.localtime(moment or timezone.now())
    if is_day_off(master, moment.date()):
        return _("Dam olishda")
    if is_working(master, moment):
        return ''
    start = next_working_start(master, moment)
    if start is None:
        return _('Hozir ishlamaydi')
    if start.date() == moment.date():
        when = start.strftime('%H:%M')
    elif start.date() == moment.date() + timedelta(days=1):
        when = _('ertaga %(t)s') % {'t': start.strftime('%H:%M')}
    else:
        when = date_format(start, 'D, H:i')
    return _('Hozir ishlamaydi — %(when)s dan') % {'when': when}


def visit_warning(master, when):
    """Kelish vaqti ustaning ish vaqtidan tashqarida bo'lsa — ogohlantirish matni."""
    if is_working(master, when):
        return ''
    if is_day_off(master, timezone.localtime(when).date()):
        return _("Bu kun dam olish kuningiz sifatida belgilangan.")
    return _("Bu vaqt ish jadvalingizdan tashqarida.")


def off_today_ids(day=None):
    from .models import DayOff
    day = day or timezone.localdate()
    return DayOff.objects.filter(start__lte=day, end__gte=day).values('master')
