from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from payments.admin import MilestoneInline

from django.db import transaction

from . import workflow
from .customer_notify import notify_master_new_order
from .models import Brand, OrderEvent, OrderPhoto, Service, ServiceRequest, Testimonial
from .phone import format_phone

admin.site.site_header = 'TechService boshqaruv paneli'
admin.site.site_title = 'TechService admin'
admin.site.index_title = 'Boshqaruv paneli'

STATUS_COLORS = {
    'Yaratildi': 'info',
    'Qabul qilindi': 'primary',
    'Joyida': 'warning',
    'Ishda': 'warning',
    'Bajarildi': 'success',
    'Tasdiqlandi': 'success',
    'Bekor qilindi': 'default',
    'Nizo': 'danger',
}


class OrderPhotoInline(TabularInline):
    model = OrderPhoto
    extra = 0
    fields = ['preview', 'kind', 'uploaded_by', 'caption', 'is_hidden', 'created_at']
    readonly_fields = ['preview', 'kind', 'uploaded_by', 'caption', 'created_at']
    verbose_name_plural = 'Rasmlar (nizoda dalil)'

    def has_add_permission(self, request, obj=None):
        return False

    @display(description='Rasm')
    def preview(self, obj):
        thumb = obj.thumbnail or obj.image
        return format_html('<a href="{}" target="_blank"><img src="{}" style="height:64px;border-radius:6px"></a>',
                           obj.image.url, thumb.url) if thumb else '—'


class OrderEventInline(TabularInline):
    model = OrderEvent
    extra = 0
    can_delete = False
    fields = ['created_at', 'status', 'actor', 'note']
    readonly_fields = fields
    verbose_name_plural = 'Buyurtma tarixi (timeline)'

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ServiceRequest)
class ServiceRequestAdmin(ModelAdmin):
    list_display = ['id', 'client', 'phone_display', 'category', 'master', 'status_badge', 'created_at']
    list_display_links = ['id', 'client']
    list_filter = ['status', 'category', 'created_at']
    list_filter_submit = True
    search_fields = ['name', 'phone', 'email', 'address', 'problem_description', 'master__full_name']
    readonly_fields = ['created_at', 'updated_at', 'consent', 'review_link']
    autocomplete_fields = ['master', 'catalog_item']
    date_hierarchy = 'created_at'
    list_per_page = 25
    actions = ['mark_cancelled']
    inlines = [MilestoneInline, OrderPhotoInline, OrderEventInline]

    fieldsets = [
        ("Mijoz", {'fields': ['name', 'phone', 'email', 'address', 'consent']}),
        ("Buyurtma", {'fields': ['category', 'master', ('catalog_item', 'quantity'), 'problem_description',
                                 'appliance_type', 'brand']}),
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
            return "Usta 'Bajarildi' deganidan keyin paydo bo'ladi"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">{0}</a><br>'
            '<small>Shu havolani mijozga yuboring (SMS/Telegram) — u ustani baholaydi.</small>',
            obj.get_review_url(),
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Admin holatni o'zgartirsa ham timeline'da ko'rinsin
        if change and 'status' in form.changed_data:
            workflow.admin_set_status(obj, obj.status, note=f'{request.user}')
        # Admin ustani biriktirsa — usta xabar oladi (avval xabar bormasdi)
        if obj.master_id and 'master' in form.changed_data:
            transaction.on_commit(lambda: notify_master_new_order(obj))

    @action(description="Tanlanganlarni bekor qilish", icon='cancel')
    def mark_cancelled(self, request, queryset):
        count = 0
        for order in queryset.exclude(status__in=[ServiceRequest.STATUS_CONFIRMED, ServiceRequest.STATUS_CANCELLED]):
            order.status = ServiceRequest.STATUS_CANCELLED
            order.save(update_fields=['status', 'updated_at'])
            workflow.admin_set_status(order, order.status, note=f'{request.user}')
            count += 1
        messages.success(request, f'{count} ta buyurtma bekor qilindi.')


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ['name', 'category', 'price_display', 'duration_minutes', 'is_popular', 'is_active', 'order']
    list_filter = ['is_active', 'is_popular', 'category', 'price_type']
    search_fields = ['name', 'name_ru', 'description']
    list_editable = ['is_popular', 'is_active', 'order']
    fieldsets = [
        (None, {'fields': ['category', 'name', 'description', 'includes']}),
        ('Narx', {'fields': [('price_from', 'price_type', 'unit'), 'duration_minutes']}),
        ('Ruscha', {'fields': ['name_ru', 'description_ru', 'includes_ru'], 'classes': ['collapse']}),
        ('Ko\'rinish', {'fields': ['is_popular', 'is_active', 'order']}),
    ]

    @display(description='Narx', ordering='price_from')
    def price_display(self, obj):
        if not obj.price_from:
            return 'Bepul'
        text = f"{obj.price_from:,.0f}".replace(',', ' ') + " so'm"
        if obj.price_type == obj.PRICE_FROM:
            text += 'dan'
        if obj.is_per_unit:
            text += f' / {obj.get_unit_display()}'
        return text


@admin.register(OrderPhoto)
class OrderPhotoAdmin(ModelAdmin):
    """Portfolio moderatsiyasi: nomaqbul rasmni saytdan yashirish (buyurtmada dalil sifatida qoladi)."""

    list_display = ['preview', 'order', 'kind', 'uploaded_by', 'master', 'in_portfolio', 'is_hidden', 'created_at']
    list_filter = ['kind', 'uploaded_by', 'is_hidden', 'created_at']
    list_editable = ['is_hidden']
    search_fields = ['order__id', 'order__master__full_name', 'caption']
    readonly_fields = ['order', 'kind', 'uploaded_by', 'image', 'thumbnail', 'created_at']
    list_per_page = 40

    def has_add_permission(self, request):
        return False

    @display(description='Rasm')
    def preview(self, obj):
        thumb = obj.thumbnail or obj.image
        return format_html('<img src="{}" style="height:56px;border-radius:6px">', thumb.url) if thumb else '—'

    @display(description='Usta')
    def master(self, obj):
        return obj.order.master or '—'

    @display(description='Portfolioda', boolean=True)
    def in_portfolio(self, obj):
        return (obj.order.status == ServiceRequest.STATUS_CONFIRMED and obj.order.photos_in_portfolio
                and obj.kind != OrderPhoto.KIND_PROBLEM and not obj.is_hidden)


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
