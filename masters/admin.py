from django.contrib import admin, messages
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from repair_service.phone import format_phone

from .models import Category, Master, Review


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ['icon_name', 'slug', 'masters_total', 'is_active', 'order']
    list_editable = ['is_active', 'order']
    prepopulated_fields = {'slug': ['name']}
    search_fields = ['name']

    @display(description='Kategoriya')
    def icon_name(self, obj):
        return f'{obj.icon} {obj.name}'

    @display(description='Ustalar')
    def masters_total(self, obj):
        return obj.masters.filter(is_verified=True).count()


class ReviewInline(TabularInline):
    model = Review
    extra = 0
    fields = ['author_name', 'quality', 'punctuality', 'price', 'politeness', 'comment', 'is_published', 'created_at']
    readonly_fields = ['author_name', 'quality', 'punctuality', 'price', 'politeness', 'comment', 'created_at']
    can_delete = True
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False  # baho faqat mijoz tomonidan, ariza orqali


@admin.register(Master)
class MasterAdmin(ModelAdmin):
    list_display = [
        'avatar_name', 'phone_display', 'categories_list', 'rating', 'reviews_count',
        'verified_badge', 'is_available', 'created_at',
    ]
    list_filter = ['is_verified', 'is_available', 'categories', 'created_at']
    list_filter_submit = True
    search_fields = ['full_name', 'phone', 'address']
    readonly_fields = ['rating_avg', 'reviews_count', 'created_at', 'updated_at', 'map_link']
    autocomplete_fields = ['user']
    filter_horizontal = ['categories']
    inlines = [ReviewInline]
    actions = ['verify', 'unverify', 'recalculate']
    list_per_page = 25

    fieldsets = [
        ('Usta', {'fields': ['user', 'full_name', 'phone', 'photo', 'categories', 'experience_years', 'bio']}),
        ('Joylashuv', {'fields': ['address', ('latitude', 'longitude'), 'map_link', 'service_radius_km']}),
        ('Holat', {'fields': ['is_verified', 'is_available']}),
        ('Reyting', {'fields': ['rating_avg', 'reviews_count', 'created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('categories')

    @display(description='Usta', ordering='full_name', header=True)
    def avatar_name(self, obj):
        return obj.full_name, obj.address or '—'

    @display(description='Telefon', ordering='phone')
    def phone_display(self, obj):
        return format_phone(obj.phone)

    @display(description="Yo'nalishlar")
    def categories_list(self, obj):
        return ', '.join(c.name for c in obj.categories.all())

    @display(description='Baho', ordering='rating_avg')
    def rating(self, obj):
        if not obj.reviews_count:
            return '—'
        return f'★ {obj.rating_avg}'

    @display(
        description='Tasdiq', ordering='is_verified',
        label={'Tasdiqlangan': 'success', 'Kutilmoqda': 'warning'},
    )
    def verified_badge(self, obj):
        return 'Tasdiqlangan' if obj.is_verified else 'Kutilmoqda'

    @display(description='Xaritada')
    def map_link(self, obj):
        if obj.latitude is None:
            return '—'
        return format_html(
            '<a href="https://yandex.uz/maps/?pt={},{}&z=15&l=map" target="_blank" rel="noopener">'
            'Yandex xaritada ochish ↗</a>', obj.longitude, obj.latitude,
        )

    @action(description='Tanlanganlarni tasdiqlash', icon='verified')
    def verify(self, request, queryset):
        updated = queryset.update(is_verified=True)
        messages.success(request, f'{updated} ta usta tasdiqlandi va saytda ko\'rinadi.')

    @action(description='Tasdiqni bekor qilish (saytdan yashirish)', icon='block')
    def unverify(self, request, queryset):
        updated = queryset.update(is_verified=False)
        messages.warning(request, f'{updated} ta usta saytdan yashirildi.')

    @action(description='Reytingni qayta hisoblash', icon='refresh')
    def recalculate(self, request, queryset):
        for master in queryset:
            master.recalculate_rating()
        messages.success(request, 'Reyting qayta hisoblandi.')


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ['author_name', 'master', 'overall_display', 'quality', 'punctuality', 'price', 'politeness',
                    'is_published', 'created_at']
    list_filter = ['is_published', 'created_at', 'master__categories']
    list_filter_submit = True
    list_editable = ['is_published']
    search_fields = ['author_name', 'comment', 'master__full_name']
    autocomplete_fields = ['master']
    readonly_fields = ['service_request', 'created_at']
    date_hierarchy = 'created_at'

    @display(description='Umumiy')
    def overall_display(self, obj):
        return f'★ {obj.overall}'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.master.recalculate_rating()  # list_editable orqali yashirilsa ham reyting yangilanadi
