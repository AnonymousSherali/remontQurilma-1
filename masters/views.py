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

from django.db import transaction
from django.utils.translation import gettext as _

from otp import services as otp
from payments import services as payments
from repair_service import workflow
from repair_service.customer_notify import notify_quote
from repair_service.forms import ServiceRequestForm
from repair_service.models import ServiceRequest

from .forms import (
    MasterProfileForm, MasterRegistrationForm, PasswordResetForm, PhoneLoginForm, QuoteForm, ReviewForm,
)
from .geo import parse_coords
from .locations import DISTRICT_CHOICES, district_coords, district_name
from payments.models import Milestone

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
            location_label = _('Joriy joylashuvingiz')

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

    form = MasterRegistrationForm(request.POST or None, request.FILES or None, request=request)
    if request.method == 'POST' and form.is_valid():
        master = form.save()
        login(request, master.user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(
            request,
            _("Ro'yxatdan o'tdingiz! Profilingiz administrator tekshiruvidan so'ng saytda ko'rinadi."),
        )
        return redirect('masters:dashboard')
    return render(request, 'masters/register.html', {'form': form, 'districts': DISTRICT_CHOICES})


def password_reset(request):
    form = PasswordResetForm(request.POST or None, request=request)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        otp.forget(request)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, _('Parol yangilandi.'))
        return redirect('masters:dashboard')
    return render(request, 'masters/password_reset.html', {'form': form})


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
        messages.info(request, _("Kabinetdan foydalanish uchun usta sifatida ro'yxatdan o'ting."))
        return redirect('masters:register')
    status = request.GET.get('status', '')
    requests_qs = master.requests.select_related('category').order_by('-created_at')
    active = (ServiceRequest.STATUS_ACCEPTED, ServiceRequest.STATUS_ARRIVED, ServiceRequest.STATUS_IN_PROGRESS)
    counts = master.requests.aggregate(
        new=Count('id', filter=Q(status=ServiceRequest.STATUS_NEW)),
        active=Count('id', filter=Q(status__in=active)),
        done=Count('id', filter=Q(status__in=(ServiceRequest.STATUS_COMPLETED, ServiceRequest.STATUS_CONFIRMED))),
    )
    filters = {
        'new': [ServiceRequest.STATUS_NEW],
        'active': list(active),
        'done': [ServiceRequest.STATUS_COMPLETED, ServiceRequest.STATUS_CONFIRMED],
        'closed': [ServiceRequest.STATUS_CANCELLED, ServiceRequest.STATUS_DISPUTED],
    }
    if status in filters:
        requests_qs = requests_qs.filter(status__in=filters[status])

    page = Paginator(requests_qs, 15).get_page(request.GET.get('page'))
    for item in page.object_list:
        item.review_link = request.build_absolute_uri(item.get_review_url())
        item.next_action = workflow.next_master_action(item)

    earnings = Milestone.objects.filter(order__master=master, state=Milestone.STATE_RELEASED)
    balance = sum((m.master_amount for m in earnings if not m.paid_out_at), 0)
    held = sum((m.master_amount for m in Milestone.objects.filter(
        order__master=master, state=Milestone.STATE_HELD)), 0)

    return render(request, 'masters/dashboard.html', {
        'master': master,
        'page': page,
        'counts': counts,
        'status': status,
        'status_tabs': [('new', _('Yangi')), ('active', _('Jarayonda')), ('done', _('Bajarilgan')),
                        ('closed', _('Bekor / nizo'))],
        'criteria': master.criteria_breakdown(),
        'balance': balance,
        'held': held,
    })


@login_required
def profile_edit(request):
    master = _get_own_master(request)
    form = MasterProfileForm(request.POST or None, request.FILES or None, instance=master)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, _('Profil saqlandi.'))
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
        _('Endi siz buyurtma qabul qilasiz.') if master.is_available
        else _("Siz qidiruvdan vaqtincha yashirildingiz. Yangi buyurtmalar kelmaydi."),
    )
    return redirect('masters:dashboard')


def _own_order(request, pk):
    master = _get_own_master(request)
    return master, get_object_or_404(ServiceRequest.objects.select_related('category'), pk=pk, master=master)


@login_required
def order_detail(request, pk):
    """Ustaning buyurtma sahifasi: timeline, mijoz ma'lumotlari, keyingi qadam, narx va to'lovlar."""
    master, order = _own_order(request, pk)
    quote = payments.get_quote(order)
    initial = {'amount': quote.amount, 'plan': quote.plan, 'note': quote.note} if quote else {}
    next_action = workflow.next_master_action(order)
    blocked = []
    needs_quote = False
    if next_action:
        target = workflow.TRANSITIONS[(workflow.MASTER, next_action[0])][1]
        blocked = payments.unfunded_for(order, target)
        needs_quote = target == ServiceRequest.STATUS_IN_PROGRESS and not payments.quote_approved(order)
    return render(request, 'orders/master.html', {
        'master': master,
        'order': order,
        'timeline': workflow.timeline(order),
        'events': order.events.all(),
        'next_action': next_action,
        'blocked_by': blocked,
        'needs_quote': needs_quote,
        'can_cancel': (workflow.MASTER, 'cancel') in workflow.TRANSITIONS
                      and order.status in workflow.TRANSITIONS[(workflow.MASTER, 'cancel')][0],
        'quote': quote,
        'quote_form': QuoteForm(initial=initial) if payments.can_quote(order) else None,
        'money': payments.summary(order),
        'review_link': request.build_absolute_uri(order.get_review_url()),
        'customer_link': request.build_absolute_uri(order.get_customer_url()),
    })


@login_required
@require_POST
def request_action(request, pk, action):
    master, order = _own_order(request, pk)
    try:
        workflow.apply(order, workflow.MASTER, action, note=request.POST.get('note', ''))
    except workflow.WorkflowError as error:
        messages.error(request, str(error))
    else:
        order.refresh_from_db()
        if order.status == ServiceRequest.STATUS_COMPLETED:
            messages.success(request, _('Ish bajarildi deb belgilandi. Mijoz natijani tasdiqlashi va baholashi kerak.'))
        else:
            messages.success(request, _('Buyurtma #%(id)s: %(status)s') % {
                'id': order.pk, 'status': order.get_status_display()})
    if request.POST.get('next') == 'dashboard':
        return redirect(f"{reverse('masters:dashboard')}?status={request.POST.get('return_status', '')}")
    return redirect(order.get_master_url())


@login_required
@require_POST
def quote_propose(request, pk):
    master, order = _own_order(request, pk)
    form = QuoteForm(request.POST)
    if form.is_valid():
        try:
            payments.propose_quote(order, form.cleaned_data['amount'], form.cleaned_data['plan'],
                                   form.cleaned_data['note'])
        except payments.PaymentError as error:
            messages.error(request, str(error))
        else:
            transaction.on_commit(lambda: notify_quote(order))
            messages.success(request, _('Narx taklifi mijozga yuborildi.'))
    else:
        messages.error(request, '; '.join(e for errs in form.errors.values() for e in errs))
    return redirect(order.get_master_url())


def review_create(request, token):
    """Mijoz bahosi. Usta "Bajarildi" degan bo'lsa — baho bilan birga buyurtma tasdiqlanadi."""
    service_request = get_object_or_404(
        ServiceRequest.objects.select_related('master'), review_token=token,
    )
    if hasattr(service_request, 'review'):
        return render(request, 'masters/review_done.html', {
            'master': service_request.master, 'already': True, 'order': service_request,
        })
    if not service_request.can_be_reviewed:
        return render(request, 'masters/review_unavailable.html', {'service_request': service_request}, status=403)

    # Tasdiqlash mablag'ni ustaga chiqaradi — shuning uchun telefon SMS bilan tasdiqlangan bo'lishi shart
    needs_confirm = service_request.status == ServiceRequest.STATUS_COMPLETED
    if needs_confirm and not otp.is_verified(request, service_request.phone):
        return render(request, 'masters/review_verify.html', {'order': service_request}, status=403)

    form = ReviewForm(request.POST or None, initial={'author_name': service_request.name})
    if request.method == 'POST' and form.is_valid():
        if needs_confirm:
            try:
                workflow.apply(service_request, workflow.CUSTOMER, 'confirm')
            except workflow.WorkflowError as error:
                messages.error(request, str(error))
                return redirect(service_request.get_customer_url())
        review = form.save(commit=False)
        review.master = service_request.master
        review.service_request = service_request
        review.save()
        return render(request, 'masters/review_done.html', {
            'master': service_request.master, 'order': service_request,
        })

    return render(request, 'masters/review_form.html', {
        'form': form, 'master': service_request.master, 'service_request': service_request,
        'needs_confirm': needs_confirm,
    })
