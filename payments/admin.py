from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from . import payouts, refunds, services, tariffs
from .models import Milestone, Payment, Payout, PromoCode, PromoRedemption, Purchase, Quote, Refund

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
    readonly_fields = ['order', 'position', 'title', 'amount', 'discount', 'release_status', 'fee_percent', 'state',
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
        messages.warning(request, f"{count} ta bosqich mijozga qaytarishga yuborildi — «Pul qaytarishlar» "
                                  "navbatini ko'ring.")

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
    search_fields = ['provider_id', 'milestone__order__id', 'milestone__order__company_inn']
    actions = ['confirm_bank_transfer']

    @action(description="Bank o'tkazmasi tushdi — bosqichni to'langan qilish", icon='account_balance')
    def confirm_bank_transfer(self, request, queryset):
        from repair_service.business import confirm_transfer
        done = sum(1 for p in queryset.filter(provider=Payment.PROVIDER_BANK) if confirm_transfer(p))
        messages.success(request, f"{done} ta bank o'tkazmasi tasdiqlandi — buyurtmalar davom etadi.")
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

    list_display = ['created_at', 'master', 'amount_display', 'status_badge', 'paid_at', 'fee_display', 'count',
                    'card_display', 'note', 'created_by']
    list_filter = ['status', 'created_at']
    list_filter_submit = True
    search_fields = ['master__full_name', 'master__phone', 'note', 'card']
    date_hierarchy = 'created_at'
    readonly_fields = ['master', 'amount', 'gross', 'fee', 'count', 'card', 'holder', 'status', 'provider',
                       'provider_ref', 'created_at', 'paid_at', 'created_by', 'orders']
    fields = readonly_fields + ['note']
    actions = ['confirm_paid', 'cancel_prepared', 'export_xlsx']

    @display(description='Holat', ordering='status', label={
        "Tayyorlangan — o'tkazilishi kerak": 'warning', "O'tkazildi": 'success', "O'tkazilmadi": 'danger'})
    def status_badge(self, obj):
        return obj.get_status_display()

    @action(description="O'tkazildi deb belgilash (ustaga xabar boradi)", icon='task_alt')
    def confirm_paid(self, request, queryset):
        count = 0
        for payout in queryset.exclude(status=Payout.STATUS_PAID):
            payouts.confirm(payout, request.user)
            count += 1
        messages.success(request, f"{count} ta o'tkazma tasdiqlandi, ustalarga xabar yuborildi.")

    @action(description="Tayyorlanganni bekor qilish (keyingi haftaga)", icon='undo')
    def cancel_prepared(self, request, queryset):
        count = sum(1 for payout in queryset if payouts.cancel_prepared(payout))
        messages.info(request, f"{count} ta tayyorlangan o'tkazma bekor qilindi — summa yana «to'lanishi kerak».")

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
        if request.method == 'POST' and request.POST.get('prepare'):
            created = payouts.prepare_weekly(force=True)
            messages.success(request, f"Tayyorlandi: {len(created)} ta o'tkazma. Ularni bank orqali o'tkazib, "
                                      "«O'tkazmalar tarixi» da «O'tkazildi» deb belgilang.")
            return redirect(reverse('admin:payments_payout_changelist') + '?status__exact=prepared')
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
            'rows': rows, 'totals': payouts.totals(rows), 'next_payout': payouts.next_payout_date(),
            'prepared': Payout.objects.filter(status=Payout.STATUS_PREPARED).count(),
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


class PromoRedemptionInline(TabularInline):
    model = PromoRedemption
    extra = 0
    can_delete = False
    fields = ['order', 'phone', 'discount', 'rewarded', 'created_at']
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PromoCode)
class PromoCodeAdmin(ModelAdmin):
    """Aksiyalar (admin yaratadi), mijozlarning referal kodlari va mukofot kodlari."""

    list_display = ['code', 'purpose', 'discount_display', 'uses', 'first_order_only', 'valid_until', 'is_active']
    list_filter = ['purpose', 'is_active', 'kind']
    list_filter_submit = True
    list_editable = ['is_active']
    search_fields = ['code', 'owner_phone', 'only_phone']
    readonly_fields = ['created_at', 'total_discount']
    inlines = [PromoRedemptionInline]
    fieldsets = [
        (None, {'fields': ['code', 'purpose', 'is_active']}),
        ('Chegirma', {'fields': [('kind', 'value'), ('max_discount', 'min_amount')],
                      'description': "Chegirma platforma hisobidan: mijoz kamroq to'laydi, usta to'liq oladi. "
                                     "Faqat onlayn to'lovda va narxning PROMO_MAX_SHARE_PERCENT foizigacha."}),
        ('Cheklovlar', {'fields': [('valid_from', 'valid_until'), ('max_uses', 'per_phone_limit'),
                                   'first_order_only', ('owner_phone', 'only_phone')]}),
        ('Natija', {'fields': ['total_discount', 'created_at']}),
    ]

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).annotate(n_uses=Count('redemptions'))

    @display(description='Chegirma')
    def discount_display(self, obj):
        text = f'{obj.value:.0f}%' if obj.kind == PromoCode.KIND_PERCENT else f"{obj.value:,.0f} so'm".replace(',', ' ')
        if obj.max_discount:
            text += f" (≤ {obj.max_discount:,.0f})".replace(',', ' ')
        return text

    @display(description='Ishlatilgan', ordering='n_uses')
    def uses(self, obj):
        return f'{obj.n_uses} / {obj.max_uses}' if obj.max_uses else obj.n_uses

    @display(description="Berilgan chegirma (so'm)")
    def total_discount(self, obj):
        total = sum((r.discount for r in obj.redemptions.all()), 0)
        return f'{total:,.0f}'.replace(',', ' ')


@admin.register(Refund)
class RefundAdmin(ModelAdmin):
    """Mijozga pul qaytarish navbati. Payme/Uzum kabinetidan bekor qilinganda o'zi yopiladi."""

    list_display = ['order_link', 'amount_display', 'provider', 'transaction', 'status_badge', 'method', 'created_at',
                    'done_at']
    list_filter = ['status', 'method', 'payment__provider']
    search_fields = ['milestone__order__id', 'milestone__order__phone', 'payment__provider_id']
    readonly_fields = ['milestone', 'payment', 'amount', 'status', 'method', 'created_at', 'done_at', 'how_to']
    fields = ['milestone', 'payment', 'amount', 'status', 'method', 'how_to', 'note', 'created_at', 'done_at']
    actions = ['mark_done', 'retry_click']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('milestone__order', 'payment')

    @display(description='Buyurtma')
    def order_link(self, obj):
        order = obj.milestone.order
        return format_html('<a href="{}">#{}</a> · {}', reverse('admin:repair_service_servicerequest_change',
                                                                  args=[order.pk]), order.pk, order.phone)

    @display(description="Summa", ordering='amount')
    def amount_display(self, obj):
        return f"{obj.amount:,.0f} so'm".replace(',', ' ')

    @display(description='Tizim')
    def provider(self, obj):
        return obj.payment.get_provider_display() if obj.payment else '—'

    @display(description='Tranzaksiya')
    def transaction(self, obj):
        return obj.payment.provider_id if obj.payment else '—'

    @display(description='Holat', ordering='status', label={
        'Qaytarilishi kerak': 'warning', 'Qaytarildi': 'success', "Avtomatik qaytarilmadi — qo'lda": 'danger'})
    def status_badge(self, obj):
        return obj.get_status_display()

    @display(description='Qanday qaytariladi')
    def how_to(self, obj):
        return refunds.instructions(obj)

    @action(description="Qaytarildi deb belgilash (kabinetdan qo'lda qaytarilgan)", icon='task_alt')
    def mark_done(self, request, queryset):
        count = 0
        for refund in queryset.exclude(status=Refund.STATUS_DONE):
            refunds.mark_manual(refund, f'{request.user}')
            count += 1
        messages.success(request, f'{count} ta qaytarish yopildi, mijozlarga xabar yuborildi.')

    @action(description='Click orqali qaytarish (API)', icon='undo')
    def retry_click(self, request, queryset):
        from django.conf import settings
        if not settings.CLICK_SECRET_KEY:
            messages.error(request, "Click sozlanmagan.")
            return
        done = 0
        for refund in queryset.exclude(status=Refund.STATUS_DONE).filter(payment__provider=Payment.PROVIDER_CLICK):
            if refunds.click_reversal(refund).status == Refund.STATUS_DONE:
                done += 1
        messages.info(request, f"Click orqali qaytarildi: {done}. Qolganlari uchun izohga qarang.")
