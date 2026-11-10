from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from otp import services as otp

from . import services, tariffs
from .models import Milestone, Payment, Purchase
from .providers import available, checkout_url, choices


def demo_checkout(request, milestone_id):
    """Soxta to'lov sahifasi — haqiqiy pul o'tmaydi. Faqat PAYMENT_PROVIDERS ichida demo bo'lsa ishlaydi.

    Haqiqiy saytda ishlatilishiga yo'l qo'ymaslik uchun DEBUG=False holatda
    ALLOW_DEMO_PAYMENTS=True alohida yoqilmagan bo'lsa 404 qaytaradi.
    """
    if 'demo' not in available() or (not settings.DEBUG and not getattr(settings, 'ALLOW_DEMO_PAYMENTS', False)):
        raise Http404
    milestone = get_object_or_404(Milestone.objects.select_related('order'), pk=milestone_id)
    order = milestone.order
    if not otp.is_verified(request, order.phone):
        raise Http404

    if request.method == 'POST':
        if milestone.state == Milestone.STATE_PENDING:
            Payment.objects.create(milestone=milestone, provider=Payment.PROVIDER_DEMO, amount=milestone.amount,
                                   state=Payment.STATE_PERFORMED)
            services.mark_held(milestone)
            messages.success(request, _("To'lov qabul qilindi. Mablag' bosqich bajarilguncha platformada ushlab turiladi."))
        return redirect(order.get_customer_url())

    return render(request, 'payments/demo_checkout.html', {'milestone': milestone, 'order': order})


# ---------- Ustalar uchun tariflar ----------

def _master_or_404(request):
    master = getattr(request.user, 'master', None)
    if master is None:
        raise Http404
    return master


@login_required
def tariffs_page(request):
    master = _master_or_404(request)
    return render(request, 'payments/tariffs.html', {
        'master': master,
        'plans': tariffs.plans(),
        'providers': choices(),
        'history': master.purchases.filter(status=Purchase.STATUS_PAID)[:10],
        'fee': settings.PLATFORM_FEE_PERCENT,
        'pro_fee': settings.PRO_FEE_PERCENT,
        'limit': settings.ACTIVE_ORDERS_LIMIT,
        'pro_limit': settings.PRO_ACTIVE_ORDERS_LIMIT,
    })


@login_required
@require_POST
def tariff_buy(request, code):
    master = _master_or_404(request)
    if tariffs.get_plan(code) is None:
        raise Http404
    purchase = tariffs.create_purchase(master, code)
    return redirect(checkout_url(purchase, request, provider=request.POST.get('provider')))


@login_required
def demo_purchase(request, purchase_id):
    """Tarif uchun soxta to'lov sahifasi (faqat sinov rejimida)."""
    if 'demo' not in available() or (not settings.DEBUG and not getattr(settings, 'ALLOW_DEMO_PAYMENTS', False)):
        raise Http404
    purchase = get_object_or_404(Purchase, pk=purchase_id, master=_master_or_404(request))
    if request.method == 'POST':
        if purchase.status == Purchase.STATUS_PENDING:
            Payment.objects.create(purchase=purchase, provider=Payment.PROVIDER_DEMO, amount=purchase.amount,
                                   state=Payment.STATE_PERFORMED)
            tariffs.activate(purchase)
            messages.success(request, _('Tarif faollashtirildi.'))
        return redirect('payments:tariffs')
    plan = tariffs.get_plan(purchase.plan)
    return render(request, 'payments/demo_checkout.html', {'purchase': purchase, 'plan': plan})
