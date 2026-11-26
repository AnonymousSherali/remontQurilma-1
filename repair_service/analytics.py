"""Yengil tahlil: mijozlar qayerdan keladi va qaysi bosqichda tushib qoladi.

Uchinchi tomon xizmati yo'q (Google Analytics va h.k.) — ma'lumot faqat o'z bazamizda:
- birinchi tashrifda manba aniqlanadi (UTM yoki yo'naltiruvchi sayt) va imzolangan cookie'ga yoziladi;
- tasodifiy tashrifchi ID (shaxsga bog'lanmaydi, IP saqlanmaydi);
- hodisalar: ommaviy sahifa ochildi, ariza formasi to'ldirila boshlandi, ariza yuborildi;
- ariza o'zi ham manbani saqlaydi — tasdiqlangan buyurtma va aylanmani manbaga bog'lash uchun;
- «Do Not Track» / «Global Privacy Control» yoqilgan brauzerlar umuman kuzatilmaydi;
- botlar hisobga olinmaydi; hodisalar ANALYTICS_RETENTION_DAYS kundan keyin o'chiriladi.
"""

import json
import re
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core import signing
from django.http import HttpResponse
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

SOURCE_COOKIE = 'ts_src'
VISITOR_COOKIE = 'ts_vid'
COOKIE_AGE = 60 * 60 * 24 * 90
# Tashrif hisoblanadigan ommaviy sahifalar (url nomi)
TRACKED_VIEWS = {'index', 'list', 'detail', 'category', 'category_district', 'catalog', 'for_masters', 'register'}
BOT_RE = re.compile(r'bot|crawl|spider|slurp|preview|monitor|curl|wget|python-requests|headless', re.I)
KNOWN_SOURCES = [  # yo'naltiruvchi sayt domeni -> (manba, kanal)
    ('google.', 'google', 'organic'), ('yandex.', 'yandex', 'organic'), ('bing.', 'bing', 'organic'),
    ('t.me', 'telegram', 'social'), ('telegram.', 'telegram', 'social'), ('instagram.', 'instagram', 'social'),
    ('facebook.', 'facebook', 'social'), ('youtube.', 'youtube', 'social'), ('olx.', 'olx', 'referral'),
]


def opted_out(request):
    return request.headers.get('DNT') == '1' or request.headers.get('Sec-GPC') == '1'


def is_bot(request):
    return bool(BOT_RE.search(request.headers.get('User-Agent', ''))) or not request.headers.get('User-Agent')


def detect_source(request):
    """UTM bo'lsa — o'sha; aks holda yo'naltiruvchi sayt; bo'lmasa — to'g'ridan-to'g'ri."""
    get = request.GET
    if get.get('utm_source'):
        return {'source': get['utm_source'][:60].lower(), 'medium': get.get('utm_medium', '')[:60].lower(),
                'campaign': get.get('utm_campaign', '')[:100]}
    if get.get('promo'):
        return {'source': 'referal', 'medium': 'referral', 'campaign': ''}
    host = (urlparse(request.headers.get('Referer', '')).hostname or '').lower()
    if host and host != request.get_host().split(':')[0]:
        for needle, source, medium in KNOWN_SOURCES:
            if needle in host:
                return {'source': source, 'medium': medium, 'campaign': ''}
        return {'source': host[:60], 'medium': 'referral', 'campaign': ''}
    return {'source': 'direct', 'medium': '', 'campaign': ''}


def attribution(request):
    """Joriy tashrifchining manbasi (cookie'dan) yoki bo'sh lug'at."""
    try:
        raw = request.get_signed_cookie(SOURCE_COOKIE, default=None, salt='ts-src', max_age=COOKIE_AGE)
        return json.loads(raw) if raw else {}
    except (signing.BadSignature, ValueError, TypeError):
        return {}


def record(request, name, path=None):
    from .models import AnalyticsEvent
    visitor = getattr(request, 'ts_visitor', '') or request.COOKIES.get(VISITOR_COOKIE, '')
    if not visitor or opted_out(request) or is_bot(request):
        return None
    src = getattr(request, 'ts_attribution', None) or attribution(request)
    return AnalyticsEvent.objects.create(
        name=name, visitor=visitor[:32], path=(path or request.path)[:200], source=src.get('source', ''),
        medium=src.get('medium', ''), campaign=src.get('campaign', ''), landing_path=src.get('landing', '')[:200])


def stamp_order(request, order):
    """Ariza yaratilganda: manbani buyurtmaga yozish va «ariza» hodisasi."""
    src = getattr(request, 'ts_attribution', None) or attribution(request)
    if src:
        order.source, order.medium = src.get('source', ''), src.get('medium', '')
        order.campaign, order.landing_path = src.get('campaign', ''), src.get('landing', '')[:200]
        order.save(update_fields=['source', 'medium', 'campaign', 'landing_path'])
    from .models import AnalyticsEvent
    record(request, AnalyticsEvent.REQUEST)


class AnalyticsMiddleware:
    """Ommaviy sahifa ochilganda: manba va tashrifchi cookie'lari, «sahifa ochildi» hodisasi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.ts_attribution = None
        request.ts_visitor = request.COOKIES.get(VISITOR_COOKIE, '')
        track = request.method == 'GET' and not opted_out(request) and not is_bot(request) and self._tracked(request)
        new_source = None
        if track:
            current = attribution(request)
            # Yangi UTM havola orqali kelsa — manba yangilanadi (oxirgi kampaniya hisobga olinadi)
            if not current or request.GET.get('utm_source') or request.GET.get('promo'):
                new_source = {**detect_source(request), 'landing': request.path}
                request.ts_attribution = new_source
            else:
                request.ts_attribution = current
            if not request.ts_visitor:
                request.ts_visitor = secrets.token_hex(8)
        response = self.get_response(request)
        if track and response.status_code == 200 and 'text/html' in response.get('Content-Type', ''):
            from .models import AnalyticsEvent
            record(request, AnalyticsEvent.PAGE_VIEW)
            secure = request.is_secure()
            if new_source:
                response.set_signed_cookie(SOURCE_COOKIE, json.dumps(new_source), salt='ts-src', max_age=COOKIE_AGE,
                                           httponly=True, samesite='Lax', secure=secure)
            if VISITOR_COOKIE not in request.COOKIES:
                response.set_cookie(VISITOR_COOKIE, request.ts_visitor, max_age=COOKIE_AGE * 4, httponly=True,
                                    samesite='Lax', secure=secure)
        return response

    @staticmethod
    def _tracked(request):
        try:
            return resolve(request.path_info).url_name in TRACKED_VIEWS
        except Resolver404:
            return False


@csrf_exempt   # faqat hodisa nomi qabul qilinadi, hech narsa o'zgartirilmaydi
@require_POST
def beacon(request):
    """Brauzerdan: «forma to'ldirish boshlandi» (navigator.sendBeacon). Javob — 204."""
    from django.core.cache import cache

    from .models import AnalyticsEvent
    visitor = request.COOKIES.get(VISITOR_COOKIE, '')
    if request.POST.get('e') == AnalyticsEvent.FORM_START and visitor:
        key = f'beacon:{visitor}:{request.POST.get("p", "")[:100]}'
        if cache.add(key, 1, 60 * 30):    # bitta sahifada yarim soatda bir marta
            record(request, AnalyticsEvent.FORM_START, path=request.POST.get('p', '')[:200] or request.path)
    return HttpResponse(status=204)


def purge(now=None):
    from .models import AnalyticsEvent
    days = getattr(settings, 'ANALYTICS_RETENTION_DAYS', 180)
    deleted, _ = AnalyticsEvent.objects.filter(created_at__lt=(now or timezone.now()) - timedelta(days=days)).delete()
    return deleted


def report(start):
    """Admin statistikasi uchun: manbalar bo'yicha voronka va kirish sahifalari."""
    from django.db.models import Count, Q, Sum

    from payments.models import Quote

    from .models import AnalyticsEvent, ServiceRequest as SR
    events = AnalyticsEvent.objects.filter(created_at__gte=start)
    visits = {r['source']: r['n'] for r in events.filter(name=AnalyticsEvent.PAGE_VIEW).values('source')
              .annotate(n=Count('visitor', distinct=True))}
    starts = {r['source']: r['n'] for r in events.filter(name=AnalyticsEvent.FORM_START).values('source')
              .annotate(n=Count('visitor', distinct=True))}
    orders = SR.objects.filter(created_at__gte=start)
    done = Q(status__in=(SR.STATUS_COMPLETED, SR.STATUS_CONFIRMED))
    by_source = {r['source'] or '': r for r in orders.order_by().values('source')
                 .annotate(requests=Count('id'), done=Count('id', filter=done))}
    gmv = {r['order__source'] or '': r['s'] for r in Quote.objects.filter(
        order__created_at__gte=start, status=Quote.STATUS_APPROVED,
        order__status__in=(SR.STATUS_COMPLETED, SR.STATUS_CONFIRMED)).values('order__source').annotate(s=Sum('amount'))}
    rows = []
    for source in set(visits) | set(starts) | set(by_source):
        r = by_source.get(source, {})
        requests_n = r.get('requests', 0)
        v = visits.get(source, 0)
        rows.append({'source': source or "noma'lum (eski arizalar)", 'visits': v, 'starts': starts.get(source, 0),
                     'requests': requests_n, 'done': r.get('done', 0), 'gmv': int(gmv.get(source) or 0),
                     'conversion': round(requests_n * 100 / v, 1) if v else None})
    rows.sort(key=lambda x: (-x['requests'], -x['visits']))
    landing = list(orders.exclude(landing_path='').order_by().values('landing_path')
                   .annotate(requests=Count('id'), done=Count('id', filter=done)).order_by('-requests')[:10])
    total_visits = events.filter(name=AnalyticsEvent.PAGE_VIEW).values('visitor').distinct().count()
    total_starts = events.filter(name=AnalyticsEvent.FORM_START).values('visitor').distinct().count()
    from masters.models import Master
    masters = list(Master.objects.filter(created_at__gte=start).order_by().values('signup_source')
                   .annotate(n=Count('id'), verified=Count('id', filter=Q(is_verified=True))).order_by('-n'))
    for m in masters:
        m['signup_source'] = m['signup_source'] or "noma'lum"
    return {'sources': rows, 'landing': landing, 'visits': total_visits, 'starts': total_starts, 'masters': masters}
