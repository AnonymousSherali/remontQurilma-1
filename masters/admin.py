from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from repair_service.phone import format_phone

from . import documents
from .models import Category, DayOff, Lesson, Master, MasterDocument, Review


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


class MasterDocumentInline(TabularInline):
    model = MasterDocument
    extra = 0
    can_delete = False
    fields = ['preview', 'kind', 'created_at']
    readonly_fields = fields
    verbose_name_plural = 'Shaxsni tasdiqlovchi hujjatlar (maxfiy)'

    def has_add_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('masters.view_masterdocument')

    @display(description='Rasm')
    def preview(self, obj):
        if not obj.pk:
            return '—'
        url = reverse('admin:masters_master_document', args=[obj.pk])
        return format_html('<a href="{0}" target="_blank" rel="noopener"><img src="{0}" alt="" '
                           'style="height:120px;border-radius:6px"></a>', url)


class DayOffInline(TabularInline):
    model = DayOff
    extra = 0
    fields = ['start', 'end', 'note']
    verbose_name_plural = 'Dam olish kunlari'


@admin.register(Master)
class MasterAdmin(ModelAdmin):
    list_display = [
        'avatar_name', 'phone_display', 'categories_list', 'rating', 'reviews_count',
        'verified_badge', 'id_badge', 'reliability_display', 'is_available', 'created_at',
    ]
    list_filter = ['is_verified', 'id_status', 'is_available', 'categories', 'created_at']
    list_filter_submit = True
    search_fields = ['full_name', 'phone', 'address']
    readonly_fields = ['rating_avg', 'reviews_count', 'created_at', 'updated_at', 'map_link', 'id_checked_at',
                       'reliability', 'reliability_data']
    autocomplete_fields = ['user']
    filter_horizontal = ['categories']
    inlines = [MasterDocumentInline, DayOffInline, ReviewInline]
    actions = ['approve_documents', 'verify', 'unverify', 'recalculate']
    list_per_page = 25

    fieldsets = [
        ('Usta', {'fields': ['user', 'full_name', 'phone', 'photo', 'categories', 'experience_years', 'bio']}),
        ('Joylashuv', {'fields': ['address', ('latitude', 'longitude'), 'map_link', 'service_radius_km']}),
        ('Holat', {'fields': ['is_verified', 'is_available']}),
        ('Ish jadvali', {'fields': ['work_days', ('work_from', 'work_to')], 'classes': ['collapse']}),
        ('Shaxsni tasdiqlash', {
            'fields': ['id_status', 'id_note', 'id_checked_at'],
            'description': "Hujjatlarni pastdagi «Shaxsni tasdiqlovchi hujjatlar» bo'limida ko'ring. "
                           "«Tasdiqlangan» — profil ham faollashadi; «Rad etilgan» — izohga sababni yozing, "
                           "usta xabar oladi va qayta yuklaydi.",
        }),
        ('Tariflar', {'fields': [('promoted_until', 'pro_until')]}),
        ('Ishonchlilik', {'fields': ['reliability', 'reliability_data'], 'classes': ['collapse']}),
        ("Pul o'tkazish", {'fields': [('payout_card', 'payout_holder')]}),
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

    @display(description='Ishonchlilik', ordering='reliability')
    def reliability_display(self, obj):
        if obj.reliability is None:
            return '—'
        d = obj.reliability_data or {}
        return format_html('<span title="Voz kechish {}% · nizo {}% · o\'z vaqtida {}">{} / 100</span>',
                           d.get('decline_rate', 0), d.get('dispute_rate', 0),
                           f"{d['on_time_rate']}%" if d.get('on_time_rate') is not None else '—', obj.reliability)

    @display(description='Hujjatlar', ordering='id_status', label={
        'Yuklanmagan': 'default', 'Tekshirilmoqda': 'warning', 'Tasdiqlangan': 'success', 'Rad etilgan': 'danger'})
    def id_badge(self, obj):
        return obj.get_id_status_display()

    def get_urls(self):
        return [path('hujjat/<int:pk>/', self.admin_site.admin_view(self.document_file), name='masters_master_document'),
                *super().get_urls()]

    def document_file(self, request, pk):
        """Maxfiy hujjat rasmini faqat huquqi bor administratorga beradi (ochiq URL yo'q)."""
        if not request.user.has_perm('masters.view_masterdocument'):
            raise PermissionDenied
        doc = get_object_or_404(MasterDocument, pk=pk)
        response = FileResponse(doc.file.open('rb'), content_type='image/jpeg')
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Disposition'] = 'inline'
        return response

    def save_model(self, request, obj, form, change):
        new_status = obj.id_status
        if change and 'id_status' in form.changed_data:
            obj.id_status = form.initial.get('id_status', obj.id_status)   # holatni documents.* o'zi qo'yadi
        super().save_model(request, obj, form, change)
        if not (change and 'id_status' in form.changed_data):
            return
        if new_status == Master.ID_APPROVED:
            documents.approve(obj)
            messages.success(request, 'Hujjatlar tasdiqlandi, profil faollashdi, ustaga xabar yuborildi.')
        elif new_status == Master.ID_REJECTED:
            try:
                documents.reject(obj, obj.id_note)
                messages.warning(request, 'Hujjatlar rad etildi, ustaga sababi yuborildi.')
            except documents.DocumentError as error:
                messages.error(request, f'Holat o\'zgarmadi: {error}')
        else:
            obj.id_status = new_status
            obj.save(update_fields=['id_status'])

    @action(description='Hujjatlarni tasdiqlash (va profilni faollashtirish)', icon='badge')
    def approve_documents(self, request, queryset):
        count = 0
        for master in queryset.filter(id_status=Master.ID_PENDING):
            documents.approve(master)
            count += 1
        messages.success(request, f"{count} ta ustaning hujjatlari tasdiqlandi. Faqat «Tekshirilmoqda» holatidagilar "
                                  "hisobga olinadi.")

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
        without_docs = queryset.exclude(id_status=Master.ID_APPROVED).count()
        updated = queryset.update(is_verified=True)
        from .onboarding import grant_welcome_bonus
        for master in queryset:            # update() signal bermaydi — bonusni alohida
            grant_welcome_bonus(master)
        messages.success(request, f'{updated} ta usta tasdiqlandi va saytda ko\'rinadi.')
        if without_docs:
            messages.warning(request, f'{without_docs} tasining hujjatlari tekshirilmagan — saytda «Hujjatlari '
                                      'tekshirilgan» belgisi chiqmaydi.')

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


@admin.register(Lesson)
class LessonAdmin(ModelAdmin):
    list_display = ['title', 'order', 'is_required', 'is_published', 'completed']
    list_editable = ['order', 'is_required', 'is_published']
    prepopulated_fields = {'slug': ['title']}
    fieldsets = [
        (None, {'fields': ['title', 'slug', 'summary', 'body', 'video_url', ('order', 'is_required', 'is_published')]}),
        ('Ruscha', {'fields': ['title_ru', 'summary_ru', 'body_ru'], 'classes': ['collapse']}),
    ]

    @display(description="O'qiganlar")
    def completed(self, obj):
        return obj.completions.count()
