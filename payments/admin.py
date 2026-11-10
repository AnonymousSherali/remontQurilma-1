from django.contrib import admin, messages
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from . import services
from . import tariffs
from .models import Milestone, Payment, Purchase, Quote

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
        updated = queryset.filter(state=Milestone.STATE_RELEASED, paid_out_at__isnull=True).update(
            paid_out_at=timezone.now())
        messages.success(request, f"{updated} ta to'lov ustaga o'tkazildi deb belgilandi.")


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
