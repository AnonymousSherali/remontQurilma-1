from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from masters.locations import DISTRICT_CHOICES
from masters.models import Category, Master, Review

from .forms import ServiceRequestForm
from .models import Brand, Service, ServiceRequest, Testimonial
from . import workflow
from .customer_notify import notify_order_created
from .notifications import notify_new_request

# Bazada brend bo'lmasa ko'rsatiladigan statik logolar (asl dizayndan)
FALLBACK_BRANDS = [
    (f'img/brand{n}.png', name) for n, name in enumerate([
        'Zanussi', 'Samsung', 'Candy', 'Siemens', 'LG', 'Bosch', 'Gorenje', 'Indesit',
        'Hansa', 'Electrolux', 'Beko', 'Ariston', 'Miele', 'Atlant', 'Ardo', 'Asko',
        'Daewoo', 'Brandt', 'Smeg', 'Vestel', 'Whirlpool', 'Zerowatt', 'Neff', 'Kaiser',
        'Renova', 'Haier', 'AEG',
    ], start=1)
]


def _landing_context():
    categories = (
        Category.objects.filter(is_active=True)
        .annotate(masters_total=Count('masters', filter=Q(masters__is_verified=True), distinct=True))
    )
    public_masters = Master.objects.public()
    top_masters = sorted(
        public_masters.filter(is_available=True).prefetch_related('categories'),
        key=lambda m: (not m.is_promoted, -m.ranking_score),
    )[:6]

    # Raqamlar bazadan olinadi — "50 000 ta mashina ta'mirladik" kabi tekshirib
    # bo'lmaydigan da'volar o'rniga haqiqiy ko'rsatkichlar.
    stats = {
        'masters': public_masters.count(),
        'categories': categories.count(),
        'completed': ServiceRequest.objects.filter(
            status__in=[ServiceRequest.STATUS_COMPLETED, ServiceRequest.STATUS_CONFIRMED]).count(),
        'rating': Review.objects.filter(is_published=True, master__is_verified=True).aggregate(
            avg=Avg(ExpressionWrapper(
                (F('quality') + F('punctuality') + F('price') + F('politeness')) / 4.0,
                output_field=FloatField(),
            )))['avg'],
    }

    reviews = list(
        Review.objects.filter(is_published=True, master__is_verified=True)
        .select_related('master')[:6]
    )
    return {
        'categories': categories,
        'top_masters': top_masters,
        'stats': stats,
        # Bosh sahifada faqat ommabop xizmatlar; to'liq ro'yxat — /narxlar/
        'services': Service.objects.filter(is_active=True, is_popular=True).select_related('category')[:12],
        'reviews': reviews,
        # Haqiqiy baholar bo'lmasa — admin kiritgan sharhlar zaxira sifatida
        'testimonials': [] if reviews else Testimonial.objects.filter(is_published=True)[:6],
        'brands': Brand.objects.filter(is_active=True),
        'fallback_brands': FALLBACK_BRANDS[:18],
        'districts': DISTRICT_CHOICES,
        'form': ServiceRequestForm(),
        'status_timeline': workflow.showcase_timeline(),
    }


def index(request):
    """Bosh sahifa"""
    return render(request, 'index.html', _landing_context())


def _client_ip(request):
    # Nginx orqasida bo'lsa, X-Real-IP ni ishonchli proksi qo'yadi.
    # X-Forwarded-For'ni to'g'ridan-to'g'ri ishlatmaymiz: uni mijoz soxtalashtira oladi.
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', '')


def _rate_limited(request):
    """Bitta IP'dan 10 daqiqada ko'pi bilan N ta ariza (spamdan himoya)."""
    limit = getattr(settings, 'REQUEST_RATE_LIMIT', 5)
    key = f'submit-rate:{_client_ip(request)}'
    count = cache.get(key, 0)
    if count >= limit:
        return True
    cache.set(key, count + 1, timeout=600)
    return False


@require_POST
def submit_request(request):
    """Ta'mirlash arizasini qabul qilish (AJAX va oddiy POST)"""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if _rate_limited(request):
        message = _("Juda ko'p ariza yuborildi. Iltimos, birozdan keyin urinib ko'ring yoki qo'ng'iroq qiling.")
        if is_ajax:
            return JsonResponse({'success': False, 'message': message}, status=429)
        return render(request, 'result.html', {'success': False, 'message': message}, status=429)

    form = ServiceRequestForm(request.POST)
    if not form.is_valid():
        errors = {field: errs[0] for field, errs in form.errors.items()}
        if is_ajax:
            return JsonResponse({'success': False, 'errors': errors}, status=400)
        context = _landing_context()
        context.update({'errors': errors, 'form': form})
        return render(request, 'index.html', context, status=400)

    service_request = form.save(commit=False)
    service_request.language = get_language() or settings.LANGUAGE_CODE
    service_request.save()
    workflow.record(service_request, ServiceRequest.STATUS_NEW, workflow.CUSTOMER)
    transaction.on_commit(lambda: notify_new_request(service_request))
    transaction.on_commit(lambda: notify_order_created(service_request))

    if service_request.master:
        message = _("Arizangiz %(master)sga yuborildi. Usta tez orada qo'ng'iroq qiladi.") % {
            'master': service_request.master.full_name}
    else:
        message = _("Arizangiz qabul qilindi! Operatorimiz eng yaqin ustani topib, siz bilan bog'lanadi.")
    track_url = service_request.get_customer_url()

    if is_ajax:
        return JsonResponse({'success': True, 'message': message, 'request_id': service_request.id,
                             'track_url': track_url})
    return render(request, 'result.html', {'success': True, 'message': message, 'track_url': track_url})


def result(request):
    """Ariza yuborish natijasi sahifasi"""
    return render(request, 'result.html', {
        'success': True,
        'message': _('Arizangiz uchun rahmat!'),
    })


def catalog(request):
    """Narxlar katalogi: yo'nalish bo'yicha filtr, qidiruv va tanlangan xizmatga buyurtma."""
    categories = Category.objects.filter(is_active=True, services__is_active=True).distinct()
    items = Service.objects.filter(is_active=True).select_related('category')

    category = None
    slug = request.GET.get('category')
    if slug:
        category = categories.filter(slug=slug).first()
        if category:
            items = items.filter(category=category)

    query = (request.GET.get('q') or '')[:100].strip()
    if query:
        items = items.filter(
            Q(name__icontains=query) | Q(name_ru__icontains=query)
            | Q(description__icontains=query) | Q(description_ru__icontains=query)
        )

    selected = None
    item_id = request.GET.get('item')
    if item_id and item_id.isdigit():
        selected = Service.objects.filter(pk=int(item_id), is_active=True).select_related('category').first()

    initial = {}
    if selected:
        initial = {'catalog_item': selected.pk, 'category': selected.category_id, 'quantity': 1}
    return render(request, 'catalog.html', {
        'categories': categories,
        'category': category,
        'items': items.order_by('category__order', 'order', 'name'),
        'query': query,
        'selected': selected,
        'form': ServiceRequestForm(initial=initial),
    })


# ---------- Yuridik sahifalar ----------

LEGAL_UPDATED = '12.11.2026'   # matn o'zgarganda yangilang


def _legal(request, template, title):
    return render(request, template, {
        'page_title': title,
        'legal': {
            'draft': settings.LEGAL_DRAFT, 'updated': LEGAL_UPDATED,
            'fee_percent': f'{settings.PLATFORM_FEE_PERCENT:g}', 'pro_fee_percent': f'{settings.PRO_FEE_PERCENT:g}',
            'auto_confirm_hours': settings.AUTO_CONFIRM_HOURS, 'auto_release_hours': settings.AUTO_RELEASE_HOURS,
            'warranty_days': settings.WARRANTY_DAYS, 'warranty_response_hours': settings.WARRANTY_RESPONSE_HOURS,
            'guarantee_max': settings.GUARANTEE_MAX_AMOUNT,
        },
    })


def offer(request):
    """Ommaviy oferta. Raqamlar (komissiya, muddatlar) sozlamalardan olinadi — matn tizim bilan mos turadi."""
    return _legal(request, 'legal/offer.html', _('Ommaviy oferta'))


def privacy(request):
    return _legal(request, 'legal/privacy.html', _('Maxfiylik siyosati'))
