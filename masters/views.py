from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from repair_service.forms import ServiceRequestForm
from repair_service.models import ServiceRequest

from .forms import MasterProfileForm, MasterRegistrationForm, PhoneLoginForm, ReviewForm
from .geo import parse_coords
from .locations import DISTRICT_CHOICES, district_coords, district_name
from .models import Category, Master
from .services import (
    DEFAULT_RADIUS_KM, RADIUS_CHOICES, SORT_DISTANCE, SORT_RATING, master_to_dict, search_masters,
)


def _search_params(request):
    """GET parametrlarini o'qish: kategoriya, joylashuv (koordinata yoki tuman), radius, saralash."""
    category = None
    slug = request.GET.get('category')
    if slug:
        category = Category.objects.filter(slug=slug, is_active=True).first()

    # Tanlangan tuman GPS'dan ustun: foydalanuvchi uni ataylab tanlagan
    # (geolokatsiya tugmasi tumanni o'zi tozalaydi).
    district = request.GET.get('district', '')
    lat, lng = district_coords(district)
    location_label = district_name(district) if lat is not None else ''
    if lat is None:
        district = ''
        lat, lng = parse_coords(request.GET.get('lat'), request.GET.get('lng'))
        if lat is not None:
            location_label = 'Joriy joylashuvingiz'

    try:
        radius = int(request.GET.get('radius', DEFAULT_RADIUS_KM))
    except ValueError:
        radius = DEFAULT_RADIUS_KM
    radius = min(max(radius, 1), 100)

    sort = request.GET.get('sort', SORT_DISTANCE)
    if sort not in (SORT_DISTANCE, SORT_RATING):
        sort = SORT_DISTANCE

    return {
        'category': category, 'lat': lat, 'lng': lng, 'district': district,
        'location_label': location_label, 'radius': radius, 'sort': sort,
        'query': request.GET.get('q', '')[:100],
    }


def master_list(request):
    params = _search_params(request)
    results = search_masters(
        category=params['category'], lat=params['lat'], lng=params['lng'],
        radius_km=params['radius'], sort=params['sort'], query=params['query'],
    )
    page = Paginator(results, 12).get_page(request.GET.get('page'))

    # Sahifalash havolalarida joriy filtrlar saqlanishi uchun
    query_without_page = request.GET.copy()
    query_without_page.pop('page', None)

    return render(request, 'masters/list.html', {
        **params,
        'page': page,
        'total': len(results),
        'categories': Category.objects.filter(is_active=True),
        'districts': DISTRICT_CHOICES,
        'radius_choices': RADIUS_CHOICES,
        'map_points': [master_to_dict(m) for m in page.object_list],
        'querystring': query_without_page.urlencode(),
    })


def api_masters(request):
    """JSON API: /api/ustalar/?category=santexnik&lat=41.3&lng=69.2&radius=10"""
    params = _search_params(request)
    results = search_masters(
        category=params['category'], lat=params['lat'], lng=params['lng'],
        radius_km=params['radius'], sort=params['sort'], query=params['query'],
    )[:50]
    return JsonResponse({
        'count': len(results),
        'results': [master_to_dict(m, request) for m in results],
    })


def master_detail(request, pk):
    master = get_object_or_404(Master.objects.prefetch_related('categories'), pk=pk)
    is_owner = request.user.is_authenticated and request.user.pk == master.user_id
    if not master.is_verified and not (is_owner or request.user.is_staff):
        raise Http404('Usta topilmadi')

    reviews = Paginator(master.reviews.filter(is_published=True), 10).get_page(request.GET.get('page'))
    form = ServiceRequestForm(initial={'master': master.pk, 'category': master.categories.first()})
    form.fields['category'].queryset = master.categories.all()

    return render(request, 'masters/detail.html', {
        'master': master,
        'is_owner': is_owner,
        'reviews': reviews,
        'criteria': master.criteria_breakdown(),
        'form': form,
        'map_points': [master_to_dict(master)],
    })


def register(request):
    if request.user.is_authenticated and hasattr(request.user, 'master'):
        return redirect('masters:dashboard')

    form = MasterRegistrationForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        master = form.save()
        login(request, master.user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(
            request,
            "Ro'yxatdan o'tdingiz! Profilingiz administrator tekshiruvidan so'ng saytda ko'rinadi.",
        )
        return redirect('masters:dashboard')
    return render(request, 'masters/register.html', {'form': form, 'districts': DISTRICT_CHOICES})


class MasterLoginView(LoginView):
    template_name = 'masters/login.html'
    authentication_form = PhoneLoginForm
    redirect_authenticated_user = True


def _get_own_master(request):
    master = getattr(request.user, 'master', None)
    if master is None:
        raise Http404("Sizda usta profili yo'q")
    return master


@login_required
def dashboard(request):
    master = getattr(request.user, 'master', None)
    if master is None:
        # Admin yoki usta profili yo'q foydalanuvchi — 404 o'rniga to'g'ri joyga
        if request.user.is_staff:
            return redirect('admin:index')
        messages.info(request, "Kabinetdan foydalanish uchun usta sifatida ro'yxatdan o'ting.")
        return redirect('masters:register')
    status = request.GET.get('status', '')
    requests_qs = master.requests.select_related('category').order_by('-created_at')
    counts = master.requests.aggregate(
        new=Count('id', filter=Q(status=ServiceRequest.STATUS_NEW)),
        in_progress=Count('id', filter=Q(status=ServiceRequest.STATUS_IN_PROGRESS)),
        completed=Count('id', filter=Q(status=ServiceRequest.STATUS_COMPLETED)),
    )
    if status in dict(ServiceRequest.STATUS_CHOICES):
        requests_qs = requests_qs.filter(status=status)

    page = Paginator(requests_qs, 15).get_page(request.GET.get('page'))
    for item in page.object_list:
        item.review_link = request.build_absolute_uri(item.get_review_url())

    return render(request, 'masters/dashboard.html', {
        'master': master,
        'page': page,
        'counts': counts,
        'status': status,
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'criteria': master.criteria_breakdown(),
    })


@login_required
def profile_edit(request):
    master = _get_own_master(request)
    form = MasterProfileForm(request.POST or None, request.FILES or None, instance=master)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profil saqlandi.')
        return redirect('masters:dashboard')
    return render(request, 'masters/profile_edit.html', {'form': form, 'master': master})


@login_required
@require_POST
def toggle_availability(request):
    master = _get_own_master(request)
    master.is_available = not master.is_available
    master.save(update_fields=['is_available'])
    messages.info(
        request,
        'Endi siz buyurtma qabul qilasiz.' if master.is_available
        else "Siz qidiruvdan vaqtincha yashirildingiz. Yangi buyurtmalar kelmaydi.",
    )
    return redirect('masters:dashboard')


# Usta qaysi holatdan qaysi holatga o'tkaza oladi. Masalan, yakunlangan
# arizani qayta "yangi" qilib bo'lmaydi — aks holda baho mantiqi buziladi.
ALLOWED_TRANSITIONS = {
    'accept': ({ServiceRequest.STATUS_NEW}, ServiceRequest.STATUS_IN_PROGRESS),
    'complete': ({ServiceRequest.STATUS_NEW, ServiceRequest.STATUS_IN_PROGRESS}, ServiceRequest.STATUS_COMPLETED),
    'cancel': ({ServiceRequest.STATUS_NEW, ServiceRequest.STATUS_IN_PROGRESS}, ServiceRequest.STATUS_CANCELLED),
}


@login_required
@require_POST
def request_action(request, pk, action):
    master = _get_own_master(request)
    service_request = get_object_or_404(ServiceRequest, pk=pk, master=master)
    if action not in ALLOWED_TRANSITIONS:
        raise Http404
    allowed_from, new_status = ALLOWED_TRANSITIONS[action]
    if service_request.status not in allowed_from:
        messages.error(request, "Bu arizaning holatini o'zgartirib bo'lmaydi.")
    else:
        service_request.status = new_status
        service_request.save(update_fields=['status', 'updated_at'])
        if new_status == ServiceRequest.STATUS_COMPLETED:
            messages.success(request, "Ariza yakunlandi. Baho havolasini mijozga yuboring — u sizning reytingingizni oshiradi.")
        else:
            messages.success(request, f'Ariza #{service_request.pk}: {service_request.get_status_display()}')
    return redirect(f"{reverse('masters:dashboard')}?status={request.POST.get('return_status', '')}")


def review_create(request, token):
    service_request = get_object_or_404(
        ServiceRequest.objects.select_related('master'), review_token=token,
    )
    if hasattr(service_request, 'review'):
        return render(request, 'masters/review_done.html', {
            'master': service_request.master, 'already': True,
        })
    if not service_request.can_be_reviewed:
        return render(request, 'masters/review_unavailable.html', {'service_request': service_request}, status=403)

    form = ReviewForm(request.POST or None, initial={'author_name': service_request.name})
    if request.method == 'POST' and form.is_valid():
        review = form.save(commit=False)
        review.master = service_request.master
        review.service_request = service_request
        review.save()
        return render(request, 'masters/review_done.html', {'master': service_request.master})

    return render(request, 'masters/review_form.html', {
        'form': form, 'master': service_request.master, 'service_request': service_request,
    })
