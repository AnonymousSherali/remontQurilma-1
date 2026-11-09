"""Buyurtmachi tomoni: buyurtmani kuzatish va boshqarish.

Buyurtmachida akkaunt yo'q. Kirish ikki xil:
- maxfiy havola /buyurtma/<kalit>/ (SMS'da yuboriladi) — faqat ko'rish;
- telefon raqami SMS kod bilan tasdiqlangan bo'lsa — amallar (tasdiqlash,
  bekor qilish, narxni qabul qilish, to'lash). Havola begona qo'lga tushsa ham
  pulga oid hech narsa qilib bo'lmaydi.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from masters.forms import QUOTE_DEVIATION_LIMIT, deviation_percent
from otp import services as otp
from payments import services as payments
from payments.models import Milestone, Quote
from payments.providers import checkout_url, choices as payment_choices

from . import workflow
from .models import ServiceRequest


def _order_by_token(token):
    return get_object_or_404(ServiceRequest.objects.select_related('master', 'category'), review_token=token)


def _can_act(request, order):
    return otp.is_verified(request, order.phone)


def order_detail(request, token):
    order = _order_by_token(token)
    can_act = _can_act(request, order)
    quote = payments.get_quote(order)
    actions = [a for a in workflow.available_actions(order, workflow.CUSTOMER)]
    milestones = list(order.milestones.all())
    for m in milestones:
        m.can_pay = can_act and m.state == Milestone.STATE_PENDING and order.status not in (
            ServiceRequest.STATUS_CANCELLED, ServiceRequest.STATUS_DISPUTED)
        m.can_release = can_act and payments.releasable(m) and m.release_status != ServiceRequest.STATUS_CONFIRMED

    return render(request, 'orders/customer.html', {
        'order': order,
        'timeline': workflow.timeline(order),
        'events': order.events.all(),
        'can_act': can_act,
        'actions': actions,
        'quote': quote,
        'milestones': milestones,
        'money': payments.summary(order),
        'payment_providers': payment_choices(),
        'estimate': order.catalog_estimate,
        'quote_deviation': deviation_percent(quote.amount, order.catalog_estimate) if quote else None,
        'deviation_limit': QUOTE_DEVIATION_LIMIT,
        'show_master_phone': order.master and order.status != ServiceRequest.STATUS_NEW,
    })


@require_POST
def order_action(request, token, action):
    order = _order_by_token(token)
    if not _can_act(request, order):
        messages.error(request, _('Avval telefon raqamingizni SMS kod bilan tasdiqlang.'))
        return redirect(order.get_customer_url())

    if action == 'confirm':
        # Tasdiqlash baho bilan birga — baho sahifasi o'zi tasdiqlaydi
        if order.status == ServiceRequest.STATUS_COMPLETED and order.can_be_reviewed:
            return redirect(order.get_review_url())
    try:
        workflow.apply(order, workflow.CUSTOMER, action, note=request.POST.get('note', ''))
    except workflow.WorkflowError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _('Buyurtma holati yangilandi.'))
    return redirect(order.get_customer_url())


@require_POST
def quote_decision(request, token, decision):
    order = _order_by_token(token)
    if not _can_act(request, order):
        raise Http404
    try:
        if decision == 'approve':
            payments.approve_quote(order)
            quote = payments.get_quote(order)
            if quote.is_online:
                messages.success(request, _("Narx kelishildi. Endi birinchi qismni to'lang — pul ustaga darhol "
                                            "o'tmaydi, bosqich bajarilguncha platformada ushlab turiladi."))
            else:
                messages.success(request, _('Narx kelishildi. To\'lovni ustaga to\'g\'ridan-to\'g\'ri qilasiz.'))
        elif decision == 'reject':
            payments.reject_quote(order)
            messages.info(request, _('Taklif rad etildi. Usta yangi narx taklif qilishi mumkin.'))
        else:
            raise Http404
    except (payments.PaymentError, Quote.DoesNotExist) as error:
        messages.error(request, str(error) or _('Taklif topilmadi'))
    return redirect(order.get_customer_url())


@require_POST
def milestone_pay(request, token, milestone_id):
    order = _order_by_token(token)
    milestone = get_object_or_404(Milestone, pk=milestone_id, order=order, state=Milestone.STATE_PENDING)
    if not _can_act(request, order):
        raise Http404
    return redirect(checkout_url(milestone, request, provider=request.POST.get('provider')))


@require_POST
def milestone_release(request, token, milestone_id):
    order = _order_by_token(token)
    milestone = get_object_or_404(Milestone, pk=milestone_id, order=order)
    if not _can_act(request, order):
        raise Http404
    try:
        payments.release(milestone)
    except payments.PaymentError as error:
        messages.error(request, str(error))
    else:
        workflow.record(order, order.status, workflow.CUSTOMER,
                        note=_("To'lov chiqarildi: %(t)s") % {'t': milestone.title})
        messages.success(request, _("Mablag' ustaga chiqarildi. Rahmat!"))
    return redirect(order.get_customer_url())


def my_orders(request):
    """SMS kod bilan tasdiqlangan raqam(lar)ga tegishli barcha buyurtmalar."""
    phones = otp.verified_phones(request)
    orders = (
        ServiceRequest.objects.filter(phone__in=phones).select_related('master', 'category')
        if phones else ServiceRequest.objects.none()
    )
    return render(request, 'orders/my_orders.html', {'orders': orders, 'phones': phones})


@require_POST
def my_orders_logout(request):
    otp.forget(request)
    return redirect(reverse('repair_service:my_orders'))
