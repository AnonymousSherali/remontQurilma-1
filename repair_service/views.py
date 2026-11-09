from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from masters.locations import DISTRICT_CHOICES
from masters.models import Category, Master, Review

from .forms import ServiceRequestForm
from .models import Brand, Service, ServiceRequest, Testimonial
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
        key=lambda m: m.ranking_score, reverse=True,
    )[:6]

    # Raqamlar bazadan olinadi — "50 000 ta mashina ta'mirladik" kabi tekshirib
    # bo'lmaydigan da'volar o'rniga haqiqiy ko'rsatkichlar.
    stats = {
        'masters': public_masters.count(),
        'categories': categories.count(),
        'completed': ServiceRequest.objects.filter(status=ServiceRequest.STATUS_COMPLETED).count(),
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
        'services': Service.objects.filter(is_active=True).select_related('category'),
        'reviews': reviews,
        # Haqiqiy baholar bo'lmasa — admin kiritgan sharhlar zaxira sifatida
        'testimonials': [] if reviews else Testimonial.objects.filter(is_published=True)[:6],
        'brands': Brand.objects.filter(is_active=True),
        'fallback_brands': FALLBACK_BRANDS[:18],
        'districts': DISTRICT_CHOICES,
        'form': ServiceRequestForm(),
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
        message = "Juda ko'p ariza yuborildi. Iltimos, birozdan keyin urinib ko'ring yoki qo'ng'iroq qiling."
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

    service_request = form.save()
    transaction.on_commit(lambda: notify_new_request(service_request))

    if service_request.master:
        message = f"Arizangiz {service_request.master.full_name}ga yuborildi. Usta tez orada qo'ng'iroq qiladi."
    else:
        message = "Arizangiz qabul qilindi! Operatorimiz eng yaqin ustani topib, siz bilan bog'lanadi."

    if is_ajax:
        return JsonResponse({'success': True, 'message': message, 'request_id': service_request.id})
    return render(request, 'result.html', {'success': True, 'message': message})


def result(request):
    """Ariza yuborish natijasi sahifasi"""
    return render(request, 'result.html', {
        'success': True,
        'message': 'Arizangiz uchun rahmat!',
    })
