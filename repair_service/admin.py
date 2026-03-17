from django.contrib import admin
from django.utils.html import format_html
from .models import ServiceRequest, Service, Testimonial, Brand

# Admin sayt sarlavhalarini o'zbekchaga o'zgartirish
admin.site.site_header = "TechService Boshqaruv Paneli"
admin.site.site_title = "TechService Admin"
admin.site.index_title = "Boshqaruv panelga xush kelibsiz"


def mark_in_progress(modeladmin, request, queryset):
    queryset.update(status='in_progress')
mark_in_progress.short_description = "Tanlanganlarni 'Jarayonda' qilish"


def mark_completed(modeladmin, request, queryset):
    queryset.update(status='completed')
mark_completed.short_description = "Tanlanganlarni 'Yakunlandi' qilish"


def mark_cancelled(modeladmin, request, queryset):
    queryset.update(status='cancelled')
mark_cancelled.short_description = "Tanlanganlarni 'Bekor qilindi' qilish"


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'phone', 'appliance_type', 'brand', 'colored_status', 'created_at']
    list_filter = ['status', 'appliance_type', 'created_at']
    search_fields = ['name', 'phone', 'email', 'problem_description']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    list_per_page = 25
    actions = [mark_in_progress, mark_completed, mark_cancelled]

    fieldsets = [
        ("Mijoz haqida ma'lumot", {
            'fields': ['name', 'phone', 'email']
        }),
        ("Texnika haqida ma'lumot", {
            'fields': ['appliance_type', 'brand', 'problem_description']
        }),
        ("Status va izohlar", {
            'fields': ['status', 'admin_notes']
        }),
        ("Tizim ma'lumotlari", {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    @admin.display(description='Holat', ordering='status')
    def colored_status(self, obj):
        colors = {
            'new': '#17a2b8',
            'in_progress': '#ffc107',
            'completed': '#28a745',
            'cancelled': '#dc3545',
        }
        labels = {
            'new': 'Yangi',
            'in_progress': 'Jarayonda',
            'completed': 'Yakunlandi',
            'cancelled': 'Bekor qilindi',
        }
        color = colors.get(obj.status, '#6c757d')
        label = labels.get(obj.status, obj.status)
        return format_html(
            '<span style="color: white; background: {}; padding: 3px 10px; '
            'border-radius: 12px; font-size: 12px; font-weight: 600;">{}</span>',
            color, label
        )


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'price_from', 'is_active', 'order']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['order', 'is_active']
    list_per_page = 20


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'star_rating', 'is_published', 'created_at']
    list_filter = ['is_published', 'rating', 'created_at']
    search_fields = ['client_name', 'text']
    list_editable = ['is_published']
    list_per_page = 20

    @admin.display(description='Reyting', ordering='rating')
    def star_rating(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: #ffc107; font-size: 16px;">{}</span>', stars)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'logo_preview', 'is_active', 'order']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['order', 'is_active']
    list_per_page = 20

    @admin.display(description='Logo')
    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height: 40px; width: auto; object-fit: contain;">',
                obj.logo.url
            )
        return '—'
