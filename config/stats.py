"""Admin: statistika sahifasi (/admin/statistika/).

Hamma ko'rsatkichlar tanlangan davrda YARATILGAN buyurtmalar bo'yicha (kogorta) — shunda
voronka bosqichlari bir xil to'plamga tegishli bo'ladi. Pul oqimi (komissiya, tariflar)
esa shu davrda sodir bo'lgan to'lovlar bo'yicha.
"""

from datetime import timedelta
from statistics import median

from django.contrib import admin
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from masters.models import Master, Review
from payments import payouts
from payments.models import Milestone, Purchase, Quote
from repair_service.models import OrderEvent, ServiceRequest as SR, WarrantyClaim

PERIODS = [(7, '7 kun'), (30, '30 kun'), (90, '90 kun'), (365, '1 yil')]


def _percent(part, whole):
    return round(part * 100 / whole, 1) if whole else None


def _money(value):
    return int(value or 0)


def collect(days=30, now=None):
    now = now or timezone.now()
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    orders = SR.objects.filter(created_at__gte=start)
    total = orders.count()

    def reached(status):
        return (OrderEvent.objects.filter(order__created_at__gte=start, status=status)
                .values('order').distinct().count())

    accepted = reached(SR.STATUS_ACCEPTED)
    completed = reached(SR.STATUS_COMPLETED)
    confirmed = orders.filter(status=SR.STATUS_CONFIRMED).count()
    cancelled = orders.filter(status=SR.STATUS_CANCELLED).count()
    disputed = reached(SR.STATUS_DISPUTED)
    waiting = orders.filter(status=SR.STATUS_NEW).count()

    funnel = [('Ariza yaratildi', total), ('Usta qabul qildi', accepted), ('Ish bajarildi', completed),
              ('Mijoz tasdiqladi', confirmed)]
    funnel = [{'label': label, 'count': count, 'percent': _percent(count, total) or 0,
               'step': _percent(count, funnel[i - 1][1]) if i else None}
              for i, (label, count) in enumerate(funnel)]

    quotes = Quote.objects.filter(order__created_at__gte=start, status=Quote.STATUS_APPROVED)
    done_quotes = quotes.filter(order__status__in=(SR.STATUS_COMPLETED, SR.STATUS_CONFIRMED))
    agg = done_quotes.aggregate(avg=Avg('amount'), gmv=Sum('amount'), n=Count('id'),
                                online=Sum('amount', filter=~Q(plan='cash')))

    released = Milestone.objects.filter(state=Milestone.STATE_RELEASED, released_at__gte=start)
    fee = sum((m.fee_amount for m in released), 0)
    tariffs = Purchase.objects.filter(status=Purchase.STATUS_PAID, paid_at__gte=start).aggregate(s=Sum('amount'))['s']

    # Qabul qilishgacha o'tgan vaqt (mediana) — birinchi "accepted" hodisasi bo'yicha
    first_accept = {}
    for order_id, created, at in (OrderEvent.objects
                                  .filter(order__created_at__gte=start, status=SR.STATUS_ACCEPTED)
                                  .order_by('created_at')
                                  .values_list('order_id', 'order__created_at', 'created_at')):
        first_accept.setdefault(order_id, (at - created).total_seconds() / 60)
    accept_minutes = round(median(first_accept.values())) if first_accept else None

    claims = WarrantyClaim.objects.filter(created_at__gte=start).count()
    reviews = Review.objects.filter(created_at__gte=start).aggregate(avg=Avg('quality'), n=Count('id'))

    by_day = {row['day']: row['n'] for row in orders.order_by().annotate(day=TruncDate('created_at'))
              .values('day').annotate(n=Count('id'))}
    step = max(days // 30, 1)   # uzun davrda ustunlarni guruhlaymiz (≤ ~30 ta ustun)
    chart = []
    for offset in range(0, days, step):
        first = (start + timedelta(days=offset)).date()
        count = sum(by_day.get(first + timedelta(days=i), 0) for i in range(step))
        chart.append({'label': first.strftime('%d.%m'), 'count': count})
    peak = max([c['count'] for c in chart] + [1])
    for c in chart:
        c['percent'] = round(c['count'] / peak * 100)

    categories = []
    done = Q(status__in=(SR.STATUS_COMPLETED, SR.STATUS_CONFIRMED))
    for row in (orders.order_by().values('category__name')
                .annotate(n=Count('id'), done=Count('id', filter=done),
                          cancelled=Count('id', filter=Q(status=SR.STATUS_CANCELLED)))
                .order_by('-n')[:12]):
        avg = done_quotes.filter(order__category__name=row['category__name']).aggregate(a=Avg('amount'))['a']
        categories.append({'name': row['category__name'] or "Yo'nalishsiz", 'count': row['n'], 'done': row['done'],
                           'conversion': _percent(row['done'], row['n']), 'cancelled': row['cancelled'],
                           'avg': _money(avg) if avg else None})

    top_masters = []
    for row in (orders.filter(done, master__isnull=False).order_by()
                .values('master', 'master__full_name', 'master__rating_avg')
                .annotate(n=Count('id')).order_by('-n')[:10]):
        gmv = done_quotes.filter(order__master_id=row['master']).aggregate(s=Sum('amount'))['s']
        top_masters.append({'id': row['master'], 'name': row['master__full_name'], 'done': row['n'],
                            'gmv': _money(gmv), 'rating': row['master__rating_avg']})

    pending = payouts.totals(payouts.pending())
    return {
        'days': days, 'start': start, 'total': total,
        'kpis': [
            {'title': 'Arizalar', 'value': total, 'footer': f'{waiting} tasi hali usta kutmoqda'},
            {'title': 'Konversiya', 'value': f'{_percent(completed, total) or 0}%',
             'footer': f'{completed} ta ish bajarildi'},
            {'title': "O'rtacha chek", 'value': f"{_money(agg['avg']):,}".replace(',', ' '),
             'footer': f"{agg['n']} ta bajarilgan ish bo'yicha, so'm"},
            {'title': 'Aylanma (GMV)', 'value': f"{_money(agg['gmv']):,}".replace(',', ' '),
             'footer': f"shundan onlayn: {_money(agg['online']):,} so'm".replace(',', ' ')},
            {'title': 'Platforma daromadi', 'value': f'{_money(fee) + _money(tariffs):,}'.replace(',', ' '),
             'footer': f"komissiya {_money(fee):,} + tariflar {_money(tariffs):,}".replace(',', ' ')},
            {'title': 'Qabul qilish tezligi',
             'value': '—' if accept_minutes is None else (
                 f'{accept_minutes} daq' if accept_minutes < 120 else f'{round(accept_minutes / 60, 1)} soat'),
             'footer': 'arizadan usta qabul qilguncha (mediana)'},
            {'title': 'Bekor qilingan', 'value': f'{_percent(cancelled, total) or 0}%', 'footer': f'{cancelled} ta ariza'},
            {'title': 'Nizolar', 'value': f'{_percent(disputed, accepted) or 0}%',
             'footer': f'{disputed} ta (qabul qilinganlarga nisbatan)'},
            {'title': 'Kafolat murojaatlari', 'value': f'{_percent(claims, confirmed) or 0}%',
             'footer': f'{claims} ta (tasdiqlanganlarga nisbatan)'},
            {'title': 'Baholar', 'value': f"★ {reviews['avg']:.1f}" if reviews['avg'] else '—',
             'footer': f"{reviews['n']} ta baho (ish sifati)"},
            {'title': 'Ustalarga qarz', 'value': f"{_money(pending['amount']):,}".replace(',', ' '),
             'footer': "chiqarilgan, lekin hali o'tkazilmagan, so'm"},
            {'title': 'Faol ustalar', 'value': orders.filter(master__isnull=False).values('master').distinct().count(),
             'footer': f"jami tasdiqlangan: {Master.objects.filter(is_verified=True).count()}"},
        ],
        'funnel': funnel, 'chart': chart, 'categories': categories, 'top_masters': top_masters,
    }


def stats_view(request):
    try:
        days = int(request.GET.get('days', 30))
    except ValueError:
        days = 30
    if days not in dict(PERIODS):
        days = 30
    context = {**admin.site.each_context(request), 'title': 'Statistika', 'periods': PERIODS, **collect(days)}
    return render(request, 'admin/stats.html', context)
