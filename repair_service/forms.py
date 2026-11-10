from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from masters.geo import in_uzbekistan, parse_coords
from masters.locations import DISTRICT_CHOICES, district_coords
from masters.models import Category, Master

from .models import Service, ServiceRequest
from .phone import normalize_phone


class ServiceRequestForm(forms.ModelForm):
    """Saytdagi barcha ariza formalari uchun yagona forma."""

    # Bot tuzog'i: odam ko'rmaydigan maydon. To'ldirilgan bo'lsa — spam.
    # Yashirin <input type=hidden> ni ko'p botlar o'tkazib yuboradi, shuning uchun
    # oddiy matn maydoni CSS bilan ekrandan tashqariga chiqariladi (.hp).
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}))
    # Joylashuv ixtiyoriy va noto'g'ri bo'lsa jimgina tashlab yuboriladi — arizani buzmasligi kerak
    latitude = forms.CharField(required=False)
    longitude = forms.CharField(required=False)
    district = forms.CharField(required=False)

    consent = forms.BooleanField(
        required=True,
        error_messages={'required': _("Shaxsiy ma'lumotlarni qayta ishlashga rozilik bering")},
    )

    class Meta:
        model = ServiceRequest
        fields = ['name', 'phone', 'email', 'address', 'district', 'latitude', 'longitude', 'category', 'master',
                  'catalog_item', 'quantity', 'problem_description', 'consent']
        error_messages = {
            'name': {'required': _('Ismingizni kiriting')},
            'phone': {'required': _('Telefon raqamni kiriting')},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['category'].required = False
        self.fields['master'].queryset = Master.objects.public()
        self.fields['master'].required = False
        self.fields['master'].error_messages['invalid_choice'] = _('Bu usta hozir buyurtma qabul qilmaydi')
        self.fields['catalog_item'].queryset = Service.objects.filter(is_active=True)
        self.fields['catalog_item'].required = False
        self.fields['quantity'].required = False
        self.fields['quantity'].min_value = 1
        self.district_choices = DISTRICT_CHOICES

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if len(name) < 2:
            raise forms.ValidationError(_("Ism kamida 2 ta belgidan iborat bo'lishi kerak"))
        return name

    def clean_phone(self):
        return normalize_phone(self.cleaned_data.get('phone'))

    def clean_email(self):
        return self.cleaned_data.get('email') or None

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise forms.ValidationError(_('Spam aniqlandi'))
        return ''

    def clean_district(self):
        slug = self.cleaned_data.get('district') or ''
        return slug if district_coords(slug)[0] is not None else ''

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity') or 1
        if not 1 <= quantity <= 999:
            raise forms.ValidationError(_("Miqdor 1 dan 999 gacha bo'lishi kerak"))
        return quantity

    def clean(self):
        cleaned = super().clean()
        master = cleaned.get('master')
        item = cleaned.get('catalog_item')
        if item and item.category_id and not cleaned.get('category'):
            cleaned['category'] = item.category  # katalogdan tanlangan xizmat yo'nalishni aniqlaydi
        if item and master and item.category_id and not master.categories.filter(pk=item.category_id).exists():
            self.add_error('catalog_item', _('Bu usta tanlangan xizmatni bajarmaydi. Boshqa ustani tanlang.'))
        # Joylashuv: tanlangan tuman GPS'dan ustun (qidiruvdagi kabi); O'zbekistondan tashqari — tashlanadi
        lat, lng = parse_coords(cleaned.get('latitude'), cleaned.get('longitude'))
        if cleaned.get('district'):
            lat, lng = district_coords(cleaned['district'])
        if lat is not None and lng is not None and in_uzbekistan(lat, lng):
            cleaned['latitude'], cleaned['longitude'] = Decimal(str(round(lat, 6))), Decimal(str(round(lng, 6)))
        else:
            cleaned['latitude'] = cleaned['longitude'] = None
        category = cleaned.get('category')
        if master and not master.is_available:
            self.add_error('master', _('Bu usta hozir buyurtma qabul qilmayapti. Boshqa ustani tanlang.'))
        if master and (not category or not master.categories.filter(pk=category.pk).exists()):
            # Santexnikka "elektrik" arizasi kabi mantiqsizlikning oldini olamiz:
            # yo'nalish ustaning o'z yo'nalishlaridan biriga keltiriladi.
            cleaned['category'] = master.categories.order_by('order').first()
        return cleaned
