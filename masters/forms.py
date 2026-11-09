from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction

from repair_service.phone import normalize_phone

from .geo import in_uzbekistan
from .locations import DISTRICT_CHOICES, district_coords
from .models import RATING_CHOICES, Category, Master, Review

MAX_PHOTO_MB = 3


class MasterProfileForm(forms.ModelForm):
    # Brauzer koordinatani 6 xonadan ko'p beradi; DecimalField uni yashirin
    # maydonda tushunarsiz xato bilan rad etardi. Float qabul qilib, o'zimiz yaxlitlaymiz.
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    district = forms.ChoiceField(
        label='Tuman', required=False, choices=[('', 'Tumanni tanlang')] + DISTRICT_CHOICES,
        help_text="Joylashuvni aniqlay olmasangiz, tumanni tanlang.",
    )

    class Meta:
        model = Master
        fields = [
            'full_name', 'categories', 'experience_years', 'bio', 'photo',
            'address', 'latitude', 'longitude', 'service_radius_km',
        ]
        widgets = {
            'categories': forms.CheckboxSelectMultiple,
            'bio': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Masalan: 8 yillik tajriba, Bosch va Samsung servis markazida ishlaganman...',
            }),
            'address': forms.TextInput(attrs={'placeholder': 'Masalan: Chilonzor, 9-kvartal'}),
        }
        error_messages = {
            'full_name': {'required': 'Ism familiyangizni kiriting'},
            'categories': {'required': "Kamida bitta yo'nalishni tanlang"},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categories'].queryset = Category.objects.filter(is_active=True)

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size') and photo.size > MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(f'Rasm hajmi {MAX_PHOTO_MB} MB dan oshmasligi kerak')
        return photo

    def clean(self):
        cleaned = super().clean()
        lat, lng = cleaned.get('latitude'), cleaned.get('longitude')
        district = cleaned.get('district')

        if (lat is None or lng is None) and district:
            d_lat, d_lng = district_coords(district)
            lat, lng = d_lat, d_lng

        if lat is None or lng is None:
            raise forms.ValidationError(
                "Joylashuvingizni aniqlang (\"Joylashuvimni aniqlash\" tugmasi) yoki tumanni tanlang"
            )
        if not in_uzbekistan(lat, lng):
            raise forms.ValidationError("Joylashuv O'zbekiston hududidan tashqarida. Qaytadan aniqlang.")

        # Model maydonlari 6 xonali — brauzer bergan uzun qiymatni moslaymiz
        cleaned['latitude'] = Decimal(str(round(float(lat), 6)))
        cleaned['longitude'] = Decimal(str(round(float(lng), 6)))
        return cleaned


class MasterRegistrationForm(MasterProfileForm):
    phone = forms.CharField(
        label='Telefon raqam', max_length=20,
        widget=forms.TextInput(attrs={'type': 'tel', 'placeholder': '+998 (90) 123-45-67', 'data-phone': ''}),
    )
    password1 = forms.CharField(label='Parol', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(label='Parolni takrorlang', strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    consent = forms.BooleanField(
        label="Shaxsiy ma'lumotlarim qayta ishlanishiga va saytda e'lon qilinishiga roziman",
        error_messages={'required': 'Davom etish uchun rozilik bering'},
    )

    field_order = ['full_name', 'phone', 'password1', 'password2', 'categories', 'experience_years', 'bio']

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get('phone'))
        username = phone.lstrip('+')
        if get_user_model().objects.filter(username=username).exists() or Master.objects.filter(phone=phone).exists():
            raise forms.ValidationError("Bu raqam bilan allaqachon ro'yxatdan o'tilgan. Kirish sahifasidan foydalaning.")
        return phone

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Parollar mos kelmadi')
        elif p1:
            user = get_user_model()(username=(cleaned.get('phone') or '').lstrip('+'),
                                    first_name=cleaned.get('full_name', ''))
            try:
                password_validation.validate_password(p1, user)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        phone = self.cleaned_data['phone']
        user = get_user_model().objects.create_user(
            username=phone.lstrip('+'),
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['full_name'][:150],
        )
        master = super().save(commit=False)
        master.user = user
        master.phone = phone
        master.is_verified = False  # admin tekshirmaguncha saytda ko'rinmaydi
        master.save()
        self.save_m2m()
        return master


class PhoneLoginForm(AuthenticationForm):
    """Ustalar telefon raqami bilan kiradi (login = raqam raqamlari)."""

    username = forms.CharField(
        label='Telefon raqam',
        widget=forms.TextInput(attrs={'type': 'tel', 'autofocus': True, 'placeholder': '+998 (90) 123-45-67', 'data-phone': ''}),
    )

    error_messages = {
        'invalid_login': "Telefon raqam yoki parol noto'g'ri.",
        'inactive': 'Bu akkaunt bloklangan.',
    }

    def clean_username(self):
        value = self.cleaned_data.get('username', '')
        try:
            return normalize_phone(value).lstrip('+')
        except forms.ValidationError:
            return value  # admin login kabi oddiy username ham ishlasin


class StarRadioSelect(forms.RadioSelect):
    template_name = 'masters/widgets/stars.html'


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['quality', 'punctuality', 'price', 'politeness', 'comment', 'author_name']
        widgets = {
            'quality': StarRadioSelect(choices=RATING_CHOICES),
            'punctuality': StarRadioSelect(choices=RATING_CHOICES),
            'price': StarRadioSelect(choices=RATING_CHOICES),
            'politeness': StarRadioSelect(choices=RATING_CHOICES),
            'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Usta haqida fikringiz (ixtiyoriy)'}),
        }
        labels = {'author_name': 'Ismingiz'}
        error_messages = {
            field: {'required': 'Baho qo\'ying'}
            for field in ('quality', 'punctuality', 'price', 'politeness')
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ModelForm tanlovlarga bo'sh "---------" ni qo'shadi — u 6-yulduz bo'lib chiqardi
        for name, _ in Review.CRITERIA:
            self.fields[name].choices = RATING_CHOICES
