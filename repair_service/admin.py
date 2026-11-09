from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Brand, Service, ServiceRequest, Testimonial
from .phone import format_phone

admin.site.site_header = 'TechService boshqaruv paneli'
admin.site.site_title = 'TechService admin'
admin.site.index_title = 'Boshqaruv paneli'

STATUS_COLORS = {
    'Yangi': 'info',
    'Jarayonda': 'warning',
    'Yakunlandi': 'success',
    'Bekor qilindi': 'danger',
}


@admin.register(ServiceRequest)
class ServiceRequestAdmin(ModelAdmin):
    list_display = ['id', 'client', 'phone_display', 'category', 'master', 'status_badge', 'created_at']
    list_display_links = ['id', 'client']
    list_filter = ['status', 'category', 'created_at']
    list_filter_submit = True
    search_fields = ['name', 'phone', 'email', 'address', 'problem_description', 'master__full_name']
    readonly_fields = ['created_at', 'updated_at', 'consent', 'review_link']
    autocomplete_fields = ['master']
    date_hierarchy = 'created_at'
    list_per_page = 25
    actions = ['mark_in_progress', 'mark_completed', 'mark_cancelled']

    fieldsets = [
        ("Mijoz", {'fields': ['name', 'phone', 'email', 'address', 'consent']}),
        ("Buyurtma", {'fields': ['category', 'master', 'problem_description', 'appliance_type', 'brand']}),
        ("Holat va izohlar", {'fields': ['status', 'admin_notes', 'review_link']}),
        ("Tizim ma'lumotlari", {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category', 'master')

    @display(description='Mijoz', ordering='name', header=True)
    def client(self, obj):
        return obj.name, obj.address or (obj.problem_description[:60] if obj.problem_description else '')

    @display(description='Telefon', ordering='phone')
    def phone_display(self, obj):
        return format_html('<a href="tel:{}">{}</a>', obj.phone, format_phone(obj.phone))

    @display(description='Holat', ordering='status', label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.get_status_display()

    @display(description='Baho havolasi')
    def review_link(self, obj):
        if hasattr(obj, 'review'):
            return format_html('✅ Mijoz baho qoldirgan: ★ {}', obj.review.overall)
        if not obj.can_be_reviewed:
            return 'Ariza yakunlangan va usta biriktirilgan bo\'lsa paydo bo\'ladi'
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">{0}</a><br>'
            '<small>Shu havolani mijozga yuboring (SMS/Telegram) — u ustani baholaydi.</small>',
            obj.get_review_url(),
        )

    def _set_status(self, request, queryset, status):
        updated = queryset.update(status=status)
        messages.success(request, f'{updated} ta ariza yangilandi.')

    @action(description="Tanlanganlarni 'Jarayonda' qilish", icon='pending')
    def mark_in_progress(self, request, queryset):
        self._set_status(request, queryset, ServiceRequest.STATUS_IN_PROGRESS)

    @action(description="Tanlanganlarni 'Yakunlandi' qilish", icon='task_alt')
    def mark_completed(self, request, queryset):
        self._set_status(request, queryset, ServiceRequest.STATUS_COMPLETED)

    @action(description="Tanlanganlarni 'Bekor qilindi' qilish", icon='cancel')
    def mark_cancelled(self, request, queryset):
        self._set_status(request, queryset, ServiceRequest.STATUS_CANCELLED)


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ['name', 'category', 'price_display', 'is_active', 'order']
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'description']
    list_editable = ['is_active', 'order']

    @display(description='Narx', ordering='price_from')
    def price_display(self, obj):
        return f"{obj.price_from:,.0f} so'mdan".replace(',', ' ') if obj.price_from else 'Bepul'


@admin.register(Testimonial)
class TestimonialAdmin(ModelAdmin):
    list_display = ['client_name', 'star_rating', 'is_published', 'created_at']
    list_filter = ['is_published', 'rating', 'created_at']
    search_fields = ['client_name', 'text']
    list_editable = ['is_published']

    @display(description='Reyting', ordering='rating')
    def star_rating(self, obj):
        return '★' * obj.rating + '☆' * (5 - obj.rating)


@admin.register(Brand)
class BrandAdmin(ModelAdmin):
    list_display = ['name', 'logo_preview', 'is_active', 'order']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['is_active', 'order']

    @display(description='Logo')
    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="height:32px;width:auto;object-fit:contain">', obj.logo.url)
        return '—'


# Foydalanuvchilar va guruhlar ham yangi dizaynda ko'rinishi uchun qayta ro'yxatdan o'tkazamiz
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
