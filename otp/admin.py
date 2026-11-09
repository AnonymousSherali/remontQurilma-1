from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import PhoneCode


@admin.register(PhoneCode)
class PhoneCodeAdmin(ModelAdmin):
    """Faqat kuzatish uchun: kim qachon kod so'radi (suiiste'molni aniqlash)."""

    list_display = ['phone', 'purpose', 'attempts', 'is_used', 'ip', 'created_at']
    list_filter = ['purpose', 'is_used', 'created_at']
    search_fields = ['phone', 'ip']
    readonly_fields = [f.name for f in PhoneCode._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
