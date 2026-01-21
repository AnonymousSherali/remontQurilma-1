from django.contrib import admin
from .models import ServiceRequest, Service, Testimonial, Brand


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'phone', 'appliance_type', 'brand', 'status', 'created_at']
    list_filter = ['status', 'created_at', 'appliance_type']
    search_fields = ['name', 'phone', 'email', 'problem_description']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = [
        ('Информация о клиенте', {
            'fields': ['name', 'phone', 'email']
        }),
        ('Информация о технике', {
            'fields': ['appliance_type', 'brand', 'problem_description']
        }),
        ('Статус и комментарии', {
            'fields': ['status', 'admin_notes']
        }),
        ('Системная информация', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'price_from', 'is_active', 'order']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    list_editable = ['order', 'is_active']


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['client_name', 'rating', 'is_published', 'created_at']
    list_filter = ['is_published', 'rating', 'created_at']
    search_fields = ['client_name', 'text']
    list_editable = ['is_published']


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'order']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['order', 'is_active']
