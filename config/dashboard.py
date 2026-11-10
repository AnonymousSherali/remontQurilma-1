"""Admin panel bosh sahifasi uchun ko'rsatkichlar (django-unfold DASHBOARD_CALLBACK)."""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from masters.models import Master, Review
from repair_service.models import ServiceRequest


def dashboard_callback(request, context):
    now = timezone.now()
    # Toshkent vaqti bo'yicha kun boshi (UTC emas, aks holda 00:00–05:00 arizalari kechagi kunga tushadi)
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    requests = ServiceRequest.objects.all()
    new_count = requests.filter(status=ServiceRequest.STATUS_NEW).count()
    unassigned = requests.filter(status=ServiceRequest.STATUS_NEW, master__isnull=True).count()
    pending_masters = Master.objects.filter(is_verified=False).order_by('-created_at')

    # Oxirgi 7 kun bo'yicha arizalar soni (oddiy ustunli grafik uchun)
    by_day = {
        row['day']: row['n']
        for row in requests.filter(created_at__gte=today - timedelta(days=6))
        .order_by()  # standart -created_at tartibi GROUP BY'ni buzmasligi uchun
        .annotate(day=TruncDate('created_at')).values('day').annotate(n=Count('id'))
    }
    days = []
    for i in range(6, -1, -1):
        day = (today - timedelta(days=i)).date()
        days.append({'label': day.strftime('%d.%m'), 'count': by_day.get(day, 0)})
    peak = max([d['count'] for d in days] + [1])
    for d in days:
        d['percent'] = round(d['count'] / peak * 100)

    variants = {'new': 'info', 'in_progress': 'warning', 'completed': 'success', 'cancelled': 'danger'}
    latest = list(requests.select_related('master', 'category')[:8])
    for item in latest:
        item.status_variant = variants.get(item.status, 'default')

    context.update({
        'kpis': [
            {
                'title': 'Yangi arizalar', 'value': new_count, 'icon': 'inbox',
                'footer': f'{unassigned} tasiga usta biriktirilmagan',
                'href': reverse('admin:repair_service_servicerequest_changelist') + '?status__exact=new',
            },
            {
                'title': 'Bugun kelgan', 'value': requests.filter(created_at__gte=today).count(), 'icon': 'today',
                'footer': f"So'nggi 7 kunda: {requests.filter(created_at__gte=week_ago).count()}",
                'href': reverse('admin:repair_service_servicerequest_changelist'),
            },
            {
                'title': 'Tasdiq kutayotgan ustalar', 'value': pending_masters.count(), 'icon': 'person_alert',
                'footer': f"Jami tasdiqlangan: {Master.objects.filter(is_verified=True).count()}",
                'href': reverse('admin:masters_master_changelist') + '?is_verified__exact=0',
            },
            {
                'title': 'Baholar (7 kun)', 'value': Review.objects.filter(created_at__gte=week_ago).count(),
                'icon': 'star', 'footer': f'Jami: {Review.objects.count()}',
                'href': reverse('admin:masters_review_changelist'),
            },
        ],
        'chart_days': days,
        'latest_requests': latest,
        'pending_masters': pending_masters.prefetch_related('categories')[:6],
    })
    return context


# Diqqat: unfold badge'ni lazy() orqali chaqiradi va bo'sh satr ham "rost" bo'lib
# qoladi — shuning uchun 0 holatida ham son qaytaramiz (aks holda bo'sh badge chiqadi).
def badge_new_requests(request):
    return str(ServiceRequest.objects.filter(status=ServiceRequest.STATUS_NEW).count())


def badge_pending_masters(request):
    return str(Master.objects.filter(is_verified=False).count())


def badge_escalated_claims(request):
    """Administrator qarorini kutayotgan kafolat murojaatlari."""
    from repair_service.models import WarrantyClaim
    return str(WarrantyClaim.objects.filter(status=WarrantyClaim.STATUS_ESCALATED).count())
