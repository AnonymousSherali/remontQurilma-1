"""Admin: nizolar (/admin/nizolar/) — ro'yxat va bitta nizo sahifasi (dalillar + qaror)."""

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from payments import services as payments
from payments.models import Milestone
from repair_service import disputes
from repair_service.models import ServiceRequest as SR


def dispute_list(request):
    return render(request, 'admin/disputes.html', {
        **admin.site.each_context(request), 'title': 'Nizolar', 'orders': disputes.open_disputes(),
        'recent': SR.objects.filter(events__actor='admin', events__note__startswith='Nizo')
                    .exclude(status=SR.STATUS_DISPUTED).distinct().order_by('-updated_at')[:10],
    })


def dispute_detail(request, pk):
    order = get_object_or_404(SR.objects.select_related('master', 'category', 'catalog_item'), pk=pk)
    if request.method == 'POST':
        if not request.user.has_perm('repair_service.change_servicerequest'):
            messages.error(request, "Qaror qabul qilish uchun «arizani o'zgartirish» huquqi kerak.")
            return redirect(request.path)
        try:
            if request.POST.get('decision') == 'withdraw':
                disputes.withdraw(order, request.POST.get('note'))
                messages.success(request, 'Nizo yopildi, buyurtma davom etadi. Ikkala tomonga xabar yuborildi.')
            else:
                result = disputes.resolve(order, request.POST.getlist('release'), request.POST.get('note'))
                messages.success(request, f"Nizo hal qilindi: ustaga {result['released']:,.0f} so'm, mijozga "
                                          f"{result['refunded']:,.0f} so'm.".replace(',', ' '))
                if result['refunded']:
                    messages.warning(request, "Qaytarish «Pul qaytarishlar» navbatiga qo'shildi: Click (yoqilgan "
                                              "bo'lsa) — avtomatik; Payme — kabinetda bekor qiling, yozuv o'zi yopiladi.")
        except disputes.DisputeError as error:
            messages.error(request, str(error))
            return redirect(request.path)
        return redirect(reverse('admin_disputes'))
    event = disputes.opened_event(order)
    return render(request, 'admin/dispute_detail.html', {
        **admin.site.each_context(request), 'title': f'Nizo · buyurtma #{order.pk}',
        'order': order, 'opened': event, 'events': order.events.all(),
        'messages_list': order.messages.all(), 'photos': order.photos.all(),
        'quote': payments.get_quote(order), 'milestones': order.milestones.all(),
        'held': [m for m in order.milestones.all() if m.state == Milestone.STATE_HELD],
        'claims': order.warranty_claims.all(), 'is_open': order.status == SR.STATUS_DISPUTED,
        'back_status': disputes.status_before(order) if order.status == SR.STATUS_DISPUTED else '',
        'status_labels': dict(SR.STATUS_CHOICES),
    })
