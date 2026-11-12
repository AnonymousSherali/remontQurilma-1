from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from . import payouts, services, tariffs
from .models import Milestone, Payment, Payout, Purchase, Quote

STATE_COLORS = {"To'lanmagan": 'default', 'Ushlab turilibdi': 'warning', 'Ustaga chiqarildi': 'success',
                'Qaytarildi': 'danger'}


class PaymentInline(TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ['provider', 'provider_id', 'amount', 'state', 'created_at', 'performed_at', 'cancelled_at']
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Milestone)
class MilestoneAdmin(ModelAdmin):
    """Nizolarni hal qilish shu yerda: ushlab turilgan mablag'ni ustaga chiqarish yoki mijozga qaytarish."""

    list_display = ['order', 'position', 'title', 'amount', 'state_badge', 'master_amount_display',
                    'released_at', 'paid_out_at']
    list_filter = ['state', 'order__status']
    search_fields = ['order__id', 'order__name', 'order__phone', 'order__master__full_name']
    readonly_fields = ['order', 'position', 'title', 'amount', 'release_status', 'fee_percent', 'state',
                       'held_at', 'released_at', 'refunded_at']
    inlines = [PaymentInline]
    actions = ['force_release', 'refund', 'mark_paid_out']

    def has_add_permission(self, request):
        return False

    @display(description='Holat', label=STATE_COLORS)
    def state_badge(self, obj):
        return obj.get_state_display()

    @display(description='Ustaga')
    def master_amount_display(self, obj):
        return f'{obj.master_amount:,.0f}'.replace(',', ' ')

    @action(description="Nizo: ustaga chiqarish (usta foydasiga)", icon='paid')
    def force_release(self, request, queryset):
        count = 0
        for m in queryset.filter(state=Milestone.STATE_HELD):
            m.state, m.released_at = Milestone.STATE_RELEASED, timezone.now()
            m.save(update_fields=['state', 'released_at'])
            count += 1
        messages.success(request, f'{count} ta bosqich ustaga chiqarildi.')

    @action(description="Nizo: mijozga qaytarish (pulni to'lov tizimi kabinetidan qaytaring!)", icon='undo')
    def refund(self, request, queryset):
        count = 0
        for m in queryset.filter(state=Milestone.STATE_HELD):
            services.refund(m)
            count += 1
        messages.warning(request, f"{count} ta bosqich 'qaytarildi' deb belgilandi. Pulni Payme kabinetidan qaytaring.")

    @action(description="Ustaning kartasiga o'tkazildi deb belgilash", icon='account_balance')
    def mark_paid_out(self, request, queryset):
        masters = set(queryset.filter(state=Milestone.STATE_RELEASED, paid_out_at__isnull=True,
                                      order__master__isnull=False).values_list('order__master_id', flat=True))
        if len(masters) != 1 or queryset.exclude(order__master_id__in=masters).exists():
            messages.error(request, "Bu amal bitta ustaning bosqichlari uchun. Bir nechta usta bilan hisob-kitob — "
                                    "«Ustalarga o'tkazmalar → To'lanishi kerak» sahifasida.")
            return
        created = payouts.mark_paid(masters, request.user)
        messages.success(request, f"O'tkazma qayd etildi: {created[0].amount:,.0f} so'm "
                                  f"(ustaning barcha kutayotgan bosqichlari).".replace(',', ' '))


class MilestoneInline(TabularInline):
    model = Milestone
    extra = 0
    can_delete = False
    fields = ['position', 'title', 'amount', 'release_status', 'state', 'held_at', 'released_at']
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Quote)
class QuoteAdmin(ModelAdmin):
    list_display = ['order', 'amount', 'plan', 'status', 'proposed_at', 'decided_at']
    list_filter = ['status', 'plan']
    search_fields = ['order__id', 'order__name', 'order__phone']
    readonly_fields = ['order', 'proposed_at', 'decided_at']


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ['id', 'provider', 'provider_id', 'milestone', 'purchase', 'amount', 'state', 'created_at',
                    'performed_at']
    list_filter = ['provider', 'state']
    search_fields = ['provider_id', 'milestone__order__id']
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Purchase)
class PurchaseAdmin(ModelAdmin):
    """Tarif xaridlari. Naqd/o'tkazma bilan to'langan bo'lsa — "Qo'lda faollashtirish" amali."""

    list_display = ['master', 'plan', 'days', 'amount', 'status', 'created_at', 'paid_at']
    list_filter = ['status', 'kind', 'plan']
    search_fields = ['master__full_name', 'master__phone']
    autocomplete_fields = ['master']
    readonly_fields = ['status', 'paid_at', 'created_at']
    actions = ['activate_manually']

    @action(description="Qo'lda faollashtirish (to'lov saytdan tashqarida olingan)", icon='task_alt')
    def activate_manually(self, request, queryset):
        count = 0
        for purchase in queryset.filter(status=Purchase.STATUS_PENDING):
            tariffs.activate(purchase)
            count += 1
        messages.success(request, f'{count} ta tarif faollashtirildi.')


XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _xlsx_response(data, name):
    response = HttpResponse(data, content_type=XLSX)
    response['Content-Disposition'] = f'attachment; filename="{name}-{timezone.localdate():%Y-%m-%d}.xlsx"'
    return response


@admin.register(Payout)
class PayoutAdmin(ModelAdmin):
    """Ustalarga o'tkazmalar tarixi. Yangi o'tkazma — «To'lanishi kerak» sahifasida."""

    list_display = ['created_at', 'master', 'amount_display', 'fee_display', 'count', 'card_display', 'note',
                    'created_by']
    list_filter = ['created_at']
    list_filter_submit = True
    search_fields = ['master__full_name', 'master__phone', 'note', 'card']
    date_hierarchy = 'created_at'
    readonly_fields = ['master', 'amount', 'gross', 'fee', 'count', 'card', 'holder', 'created_at', 'created_by',
                       'orders']
    fields = readonly_fields + ['note']
    actions = ['export_xlsx']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # moliyaviy yozuv — o'chirilmaydi

    def get_urls(self):
        return [path('pending/', self.admin_site.admin_view(self.pending_view), name='payments_payout_pending'),
                *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        total = payouts.totals(payouts.pending())['amount']
        if total:
            messages.info(request, f"To'lanishi kerak: {total:,.0f} so'm.".replace(',', ' '))
        return super().changelist_view(request, extra_context)

    def pending_view(self, request):
        rows = payouts.pending()
        if request.GET.get('format') == 'xlsx':
            return _xlsx_response(payouts.pending_xlsx(rows), 'tolanishi-kerak')
        if request.method == 'POST':
            ids = [int(v) for v in request.POST.getlist('master') if v.isdigit()]
            allowed = {r['master'].pk for r in rows if r['has_card']}
            created = payouts.mark_paid([i for i in ids if i in allowed], request.user, request.POST.get('note', ''))
            if created:
                total = sum((p.amount for p in created), 0)
                messages.success(request, f"{len(created)} ta ustaga o'tkazma qayd etildi: {total:,.0f} so'm."
                                 .replace(',', ' '))
            else:
                messages.warning(request, 'Hech kim tanlanmadi.')
            return redirect(reverse('admin:payments_payout_pending'))
        for row in rows:
            row['card'] = payouts.card_display(row['master'].payout_card)
        return render(request, 'admin/payouts_pending.html', {
            **self.admin_site.each_context(request), 'title': "Ustalarga to'lanishi kerak",
            'rows': rows, 'totals': payouts.totals(rows),
        })

    @display(description="O'tkazilgan", ordering='amount')
    def amount_display(self, obj):
        return f"{obj.amount:,.0f} so'm".replace(',', ' ')

    @display(description='Komissiya', ordering='fee')
    def fee_display(self, obj):
        return f'{obj.fee:,.0f}'.replace(',', ' ')

    @display(description='Karta')
    def card_display(self, obj):
        return payouts.card_display(obj.card) or '—'

    @display(description='Buyurtmalar')
    def orders(self, obj):
        return ', '.join(f'#{m.order_id} ({m.title})' for m in obj.milestones.all()) or '—'

    @action(description="Tanlanganlarni Excel'ga yuklash", icon='download')
    def export_xlsx(self, request, queryset):
        return _xlsx_response(payouts.history_xlsx(queryset), 'otkazmalar')
