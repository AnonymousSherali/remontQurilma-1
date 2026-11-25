"""Admin: «Yordam» suhbatlari (/admin/yordam/) — javob kutayotganlar yuqorida."""

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from repair_service import support
from repair_service.models import ServiceRequest, SupportThread


def support_list(request):
    waiting = support.unanswered()
    waiting_ids = {t.pk for t in waiting}
    recent = [t for t in SupportThread.objects.prefetch_related('messages')[:50] if t.pk not in waiting_ids]
    for thread in waiting + recent:
        msgs = list(thread.messages.all())
        thread.last = msgs[-1] if msgs else None
    return render(request, 'admin/support_list.html', {
        **admin.site.each_context(request), 'title': 'Yordam suhbatlari', 'waiting': waiting, 'recent': recent})


def support_thread(request, pk):
    thread = get_object_or_404(SupportThread.objects.select_related('master'), pk=pk)
    if request.method == 'POST':
        if request.POST.get('close'):
            thread.is_closed = True
            thread.save(update_fields=['is_closed'])
            messages.info(request, 'Suhbat yopildi.')
            return redirect(reverse('admin_support'))
        try:
            support.reply(thread, request.user, request.POST.get('text'))
            messages.success(request, 'Javob yuborildi.')
        except support.SupportError as error:
            messages.error(request, str(error))
        return redirect(request.path)
    return render(request, 'admin/support_thread.html', {
        **admin.site.each_context(request), 'title': f'Yordam #{thread.pk}', 'thread': thread,
        'messages_list': thread.messages.all(),
        'orders': (thread.master.requests.all()[:5] if thread.master_id
                   else ServiceRequest.objects.filter(phone=thread.phone)[:5] if thread.phone else []),
    })
