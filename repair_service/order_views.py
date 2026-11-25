"""Buyurtmachi tomoni: buyurtmani kuzatish va boshqarish.

Buyurtmachida akkaunt yo'q. Kirish ikki xil:
- maxfiy havola /buyurtma/<kalit>/ (SMS'da yuboriladi) — faqat ko'rish;
- telefon raqami SMS kod bilan tasdiqlangan bo'lsa — amallar (tasdiqlash,
  bekor qilish, narxni qabul qilish, to'lash). Havola begona qo'lga tushsa ham
  pulga oid hech narsa qilib bo'lmaydi.
"""

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from masters.forms import QUOTE_DEVIATION_LIMIT, deviation_percent
from otp import services as otp
from payments import services as payments
from payments.models import Milestone, Quote
from payments.providers import checkout_url, choices as payment_choices

from . import photos as photo_rules
from . import chat, schedule, warranty, workflow
from .models import OrderPhoto, ServiceRequest, WarrantyClaim


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
        **photo_context(request, order, workflow.CUSTOMER if can_act else None,
                        reverse('repair_service:order_photo_upload', args=[order.review_token]),
                        'repair_service:order_photo_delete', [order.review_token]),
        'show_master_phone': order.master and order.status != ServiceRequest.STATUS_NEW,
        **promo_context(request, order, can_act),
        'reorder': reorder_target(order) if order.status == ServiceRequest.STATUS_CONFIRMED else (None, 'status'),
        **warranty.context(order),
        **chat.context(order, chat.CUSTOMER, can_act),
        'chat_url': reverse('repair_service:order_chat', args=[order.review_token]),
        'preferred_label': schedule.preferred_label(order),
    })


@require_POST
def order_action(request, token, action):
    order = _order_by_token(token)
    if not _can_act(request, order):
        messages.error(request, _('Avval telefon raqamingizni SMS kod bilan tasdiqlang.'))
        return redirect(order.get_customer_url())

    if action == 'dispute' and len(request.POST.get('note', '').strip()) < 10:
        messages.error(request, _('Muammoni qisqacha yozing (kamida 10 ta belgi) — administrator shunga qarab qaror qiladi.'))
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


def promo_context(request, order, can_act):
    from payments import promos
    from payments.models import PromoRedemption
    redemption = PromoRedemption.objects.filter(order=order).select_related('promo').first()
    referral = None
    if can_act and order.status == ServiceRequest.STATUS_CONFIRMED and promos.can_refer(order.phone):
        code = promos.referral_code_for(order.phone)
        link = request.build_absolute_uri(reverse('repair_service:index') + f'?promo={code.code}')
        referral = {'code': code, 'link': link, 'used': code.redemptions.count(),
                    'percent': code.value, 'max': code.max_discount}
    return {
        'promo': redemption,
        'promo_discount': promos.total_discount(order),
        'promo_can_change': can_act and promos.can_apply(order),
        'referral': referral,
    }


@require_POST
def promo_apply(request, token):
    from payments import promos
    order = _order_by_token(token)
    if not _can_act(request, order):
        raise Http404
    if request.POST.get('remove'):
        promos.remove(order)
        messages.info(request, _("Promo-kod olib tashlandi."))
        return redirect(order.get_customer_url() + '#promo')
    try:
        redemption = promos.apply(order, request.POST.get('code', ''))
    except promos.PromoError as error:
        messages.error(request, str(error))
    else:
        if redemption.discount:
            messages.success(request, _("Promo-kod qo'llandi: %(d)s so'm chegirma.") % {
                'd': f'{int(redemption.discount):,}'.replace(',', ' ')})
        else:
            messages.success(request, _("Promo-kod saqlandi. Chegirma usta narx taklif qilgach, onlayn to'lovda "
                                        "hisoblanadi."))
    return redirect(order.get_customer_url() + '#promo')


def chat_endpoint(request, order, viewer, back_url):
    """Ikkala tomon uchun umumiy: GET — yangi xabarlar (JSON), POST — yuborish."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    error = None
    if request.method == 'POST':
        try:
            chat.send(order, viewer, request.POST.get('text', ''))
        except chat.ChatError as exc:
            error = str(exc)
        if not is_ajax:
            if error:
                messages.error(request, error)
            return redirect(back_url + '#chat')
    try:
        after = max(int(request.GET.get('after') or request.POST.get('after') or 0), 0)
    except ValueError:
        after = 0
    return JsonResponse({
        'messages': [chat.serialize(m, viewer) for m in chat.fetch(order, viewer, after)],
        'can_send': chat.can_send(order),
        'error': error,
    }, status=400 if error else 200)


def order_chat(request, token):
    order = _order_by_token(token)
    if not _can_act(request, order):
        raise Http404
    return chat_endpoint(request, order, chat.CUSTOMER, order.get_customer_url())


@require_POST
def warranty_claim(request, token):
    order = _order_by_token(token)
    if not _can_act(request, order):
        raise Http404
    try:
        warranty.file_claim(order, request.POST.get('description', ''))
    except warranty.WarrantyError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("Murojaatingiz ustaga yuborildi. Muammoni rasmga olib qo'shsangiz, tezroq hal bo'ladi."))
    return redirect(order.get_customer_url() + '#kafolat')


@require_POST
def warranty_action(request, token, claim_id, action):
    order = _order_by_token(token)
    claim = get_object_or_404(WarrantyClaim, pk=claim_id, order=order)
    if not _can_act(request, order) or action not in ('resolve', 'escalate'):
        raise Http404
    try:
        if action == 'resolve':
            warranty.customer_resolve(claim)
            messages.success(request, _('Rahmat! Murojaat yopildi.'))
        else:
            warranty.customer_escalate(claim)
            messages.info(request, _("Murojaat administratorga o'tkazildi. Siz bilan bog'lanamiz."))
    except warranty.WarrantyError as error:
        messages.error(request, str(error))
    return redirect(order.get_customer_url() + '#kafolat')


def reorder_target(order):
    """Shu buyurtma ustasini qayta chaqirish mumkinmi: (usta, sabab). Mumkin bo'lsa sabab None."""
    from masters.models import Master
    if order.master_id is None or order.status != ServiceRequest.STATUS_CONFIRMED:
        return None, 'status'
    master = Master.objects.public().filter(pk=order.master_id).first()
    if master is None:
        return None, 'gone'
    if not master.is_available:
        return master, 'busy'
    return master, None


def reorder(request, token):
    """«Shu ustani qayta chaqirish»: ism, telefon, manzil va joylashuv avvalgi buyurtmadan olinadi."""
    from .forms import ServiceRequestForm
    from .views import _rate_limited, create_order
    order = _order_by_token(token)
    if not _can_act(request, order):
        messages.error(request, _('Avval telefon raqamingizni SMS kod bilan tasdiqlang.'))
        return redirect(order.get_customer_url())
    master, problem = reorder_target(order)
    if problem:
        if problem == 'busy':
            messages.warning(request, _("%(name)s hozir buyurtma qabul qilmayapti. Boshqa ustani tanlang.") % {
                'name': master.full_name})
        elif problem == 'gone':
            messages.warning(request, _("Bu usta hozir saytda ishlamayapti. Boshqa ustani tanlang."))
        else:
            raise Http404
        url = reverse('masters:list') + (f'?category={order.category.slug}' if order.category else '')
        return redirect(url)

    category = order.category if order.category and master.categories.filter(pk=order.category_id).exists() \
        else master.categories.order_by('order').first()
    form = None
    if request.method == 'POST':
        if _rate_limited(request):
            messages.error(request, _("Juda ko'p ariza yuborildi. Iltimos, birozdan keyin urinib ko'ring."))
            return redirect(order.get_customer_url())
        data = {
            'name': order.name, 'phone': order.phone, 'master': master.pk,
            'category': category.pk if category else '',
            'address': request.POST.get('address', order.address),
            'district': order.district,
            'latitude': str(order.latitude) if order.latitude is not None else '',
            'longitude': str(order.longitude) if order.longitude is not None else '',
            'problem_description': request.POST.get('problem_description', ''),
            'preferred_date': request.POST.get('preferred_date', ''),
            'preferred_slot': request.POST.get('preferred_slot', ''),
            'consent': request.POST.get('consent', ''),
        }
        form = ServiceRequestForm(data)
        if form.is_valid():
            new = create_order(form, note=_('Qayta chaqiruv: #%(id)s') % {'id': order.pk})
            ServiceRequest.objects.filter(pk=new.pk).update(source='qayta', medium='reorder')
            if order.telegram_chat_id:   # Telegram'da kuzatayotgan bo'lsa — yangi buyurtma ham o'sha chatga
                ServiceRequest.objects.filter(pk=new.pk).update(telegram_chat_id=order.telegram_chat_id)
            messages.success(request, _("Buyurtma %(name)sga yuborildi. Usta tez orada bog'lanadi.") % {
                'name': master.full_name})
            return redirect(new.get_customer_url())
    if form is None:
        form = ServiceRequestForm(initial={'address': order.address})
    return render(request, 'orders/reorder.html', {
        'order': order, 'master': master, 'category': category, 'form': form,
    })


def my_orders(request):
    """SMS kod bilan tasdiqlangan raqam(lar)ga tegishli barcha buyurtmalar."""
    phones = otp.verified_phones(request)
    orders = list(
        ServiceRequest.objects.filter(phone__in=phones).select_related('master', 'category')
        if phones else ServiceRequest.objects.none()
    )
    # Bir ustani faqat eng so'nggi tasdiqlangan buyurtmasida qayta chaqirish tugmasi
    seen = set()
    for item in orders:
        item.can_reorder = (item.status == ServiceRequest.STATUS_CONFIRMED and item.master_id
                            and item.master_id not in seen and item.master.is_verified)
        if item.can_reorder:
            seen.add(item.master_id)
    return render(request, 'orders/my_orders.html', {'orders': orders, 'phones': phones})


@require_POST
def my_orders_logout(request):
    otp.forget(request)
    return redirect(reverse('repair_service:my_orders'))


# ---------- Rasmlar ----------

def photo_context(request, order, actor, upload_url, delete_url_name, delete_args):
    """Buyurtma sahifasidagi rasmlar bloki uchun kontekst (ikkala tomon uchun umumiy)."""
    photos = list(order.photos.all())
    for photo in photos:
        photo.deletable = photo_rules.can_delete(photo, actor)
        if photo.deletable:
            photo.delete_url = reverse(delete_url_name, args=[*delete_args, photo.pk])
    kinds = photo_rules.allowed_kinds(order, actor)
    kind_labels = dict(OrderPhoto.KIND_CHOICES)
    return {
        'photos': photos,
        'photo_groups': [(kind, kind_labels[kind], [p for p in photos if p.kind == kind])
                         for kind, _label in OrderPhoto.KIND_CHOICES if any(p.kind == kind for p in photos)],
        'photo_kinds': [(k, kind_labels[k]) for k in kinds],
        'photo_upload_url': upload_url,
        'photo_limit': photo_rules.MAX_PHOTOS_PER_SIDE,
        # Ish boshlanmagan bo'lsa — "oldin", boshlangan bo'lsa — "keyin" rasmi kutiladi
        'photo_default_kind': (OrderPhoto.KIND_AFTER if order.reached(ServiceRequest.STATUS_IN_PROGRESS)
                               else OrderPhoto.KIND_BEFORE) if len(kinds) > 1 else (kinds[0] if kinds else ''),
    }


def handle_photo_upload(request, order, actor):
    files = request.FILES.getlist('images')
    if not files:
        messages.error(request, _('Rasm tanlang'))
        return
    added, errors = photo_rules.add_photos(order, actor, request.POST.get('kind', ''), files,
                                           request.POST.get('caption', ''))
    for error in errors:
        messages.error(request, error)
    if added:
        workflow.record(order, order.status, actor, note=_('%(n)s ta rasm yuklandi') % {'n': added})
        messages.success(request, _('%(n)s ta rasm yuklandi') % {'n': added})


@require_POST
def order_photo_upload(request, token):
    order = _order_by_token(token)
    if not _can_act(request, order):
        raise Http404
    handle_photo_upload(request, order, workflow.CUSTOMER)
    return redirect(order.get_customer_url() + '#rasmlar')


@require_POST
def order_photo_delete(request, token, photo_id):
    order = _order_by_token(token)
    photo = get_object_or_404(OrderPhoto, pk=photo_id, order=order)
    if not _can_act(request, order) or not photo_rules.can_delete(photo, workflow.CUSTOMER):
        raise Http404
    photo.delete()
    messages.info(request, _("Rasm o'chirildi."))
    return redirect(order.get_customer_url() + '#rasmlar')


@require_POST
def order_portfolio_toggle(request, token):
    order = _order_by_token(token)
    if not _can_act(request, order):
        raise Http404
    order.photos_in_portfolio = not order.photos_in_portfolio
    order.save(update_fields=['photos_in_portfolio'])
    messages.info(request, _("Ish rasmlari usta portfoliosida ko'rsatiladi.") if order.photos_in_portfolio
                  else _("Ish rasmlari usta portfoliosida ko'rsatilmaydi."))
    return redirect(order.get_customer_url() + '#rasmlar')
