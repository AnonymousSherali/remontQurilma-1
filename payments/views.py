from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from otp import services as otp

from . import services
from .models import Milestone, Payment
from .providers import provider_name


def demo_checkout(request, milestone_id):
    """Soxta to'lov sahifasi — haqiqiy pul o'tmaydi. Faqat PAYMENT_PROVIDER=demo bo'lsa ishlaydi.

    Haqiqiy saytda ishlatilishiga yo'l qo'ymaslik uchun DEBUG=False holatda
    ALLOW_DEMO_PAYMENTS=True alohida yoqilmagan bo'lsa 404 qaytaradi.
    """
    if provider_name() != 'demo' or (not settings.DEBUG and not getattr(settings, 'ALLOW_DEMO_PAYMENTS', False)):
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
