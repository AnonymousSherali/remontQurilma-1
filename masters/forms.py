from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction

from django.utils.translation import gettext_lazy as _

from otp import services as otp
from otp.models import PhoneCode
from payments.plans import PLAN_CHOICES
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
        label=_('Tuman'), required=False, choices=[('', _('Tumanni tanlang'))] + DISTRICT_CHOICES,
        help_text=_("Joylashuvni aniqlay olmasangiz, tumanni tanlang."),
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
                'placeholder': _('Masalan: 8 yillik tajriba, Bosch va Samsung servis markazida ishlaganman...'),
            }),
            'address': forms.TextInput(attrs={'placeholder': _('Masalan: Chilonzor, 9-kvartal')}),
        }
        labels = {
            'full_name': _('Ism familiya'), 'categories': _("Yo'nalishlar"), 'experience_years': _('Tajriba (yil)'),
            'bio': _("O'zingiz haqingizda"), 'photo': _('Rasm'), 'address': _('Hudud'),
            'service_radius_km': _('Xizmat radiusi (km)'),
        }
        help_texts = {
            'address': _("Saytda ko'rinadi. Aniq uy manzilini yozmang — tuman yoki mahalla yetarli."),
            'service_radius_km': _('Qancha uzoqlikdagi buyurtmalarga borasiz'),
        }
        error_messages = {
            'full_name': {'required': _('Ism familiyangizni kiriting')},
            'categories': {'required': _("Kamida bitta yo'nalishni tanlang")},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categories'].queryset = Category.objects.filter(is_active=True)

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size') and photo.size > MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(_('Rasm hajmi %(mb)s MB dan oshmasligi kerak') % {'mb': MAX_PHOTO_MB})
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
                _("Joylashuvingizni aniqlang (\"Joylashuvimni aniqlash\" tugmasi) yoki tumanni tanlang")
            )
        if not in_uzbekistan(lat, lng):
            raise forms.ValidationError(_("Joylashuv O'zbekiston hududidan tashqarida. Qaytadan aniqlang."))

        # Model maydonlari 6 xonali — brauzer bergan uzun qiymatni moslaymiz
        cleaned['latitude'] = Decimal(str(round(float(lat), 6)))
        cleaned['longitude'] = Decimal(str(round(float(lng), 6)))
        return cleaned


class MasterRegistrationForm(MasterProfileForm):
    phone = forms.CharField(
        label=_('Telefon raqam'), max_length=20,
        widget=forms.TextInput(attrs={'type': 'tel', 'placeholder': '+998 (90) 123-45-67', 'data-phone': ''}),
    )
    password1 = forms.CharField(label=_('Parol'), strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(label=_('Parolni takrorlang'), strip=False, widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    consent = forms.BooleanField(
        label=_("Shaxsiy ma'lumotlarim qayta ishlanishiga va saytda e'lon qilinishiga roziman"),
        error_messages={'required': _('Davom etish uchun rozilik bering')},
    )

    field_order = ['full_name', 'phone', 'password1', 'password2', 'categories', 'experience_years', 'bio']

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get('phone'))
        # Raqam haqiqatan shu odamniki ekanini SMS kod bilan tekshiramiz
        if self.request is not None and not otp.is_verified(self.request, phone, PhoneCode.PURPOSE_REGISTER):
            raise forms.ValidationError(_('Telefon raqamni SMS kod bilan tasdiqlang'))
        username = phone.lstrip('+')
        if get_user_model().objects.filter(username=username).exists() or Master.objects.filter(phone=phone).exists():
            raise forms.ValidationError(_("Bu raqam bilan allaqachon ro'yxatdan o'tilgan. Kirish sahifasidan foydalaning."))
        return phone

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', _('Parollar mos kelmadi'))
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
        label=_('Telefon raqam'),
        widget=forms.TextInput(attrs={'type': 'tel', 'autofocus': True, 'placeholder': '+998 (90) 123-45-67', 'data-phone': ''}),
    )

    error_messages = {
        'invalid_login': _("Telefon raqam yoki parol noto'g'ri."),
        'inactive': _('Bu akkaunt bloklangan.'),
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
            'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': _('Usta haqida fikringiz (ixtiyoriy)')}),
        }
        labels = {
            'author_name': _('Ismingiz'), 'comment': _('Izoh'), 'quality': _('Ish sifati'),
            'punctuality': _("O'z vaqtida kelishi"), 'price': _('Narx adolatliligi'), 'politeness': _('Muomala madaniyati'),
        }
        error_messages = {
            field: {'required': _('Baho qo\'ying')}
            for field in ('quality', 'punctuality', 'price', 'politeness')
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ModelForm tanlovlarga bo'sh "---------" ni qo'shadi — u 6-yulduz bo'lib chiqardi
        for name, _ in Review.CRITERIA:
            self.fields[name].choices = RATING_CHOICES


# Usta narxi katalogdan shuncha foizdan ko'p farq qilsa — sababini yozishi shart
QUOTE_DEVIATION_LIMIT = 20


def deviation_percent(amount, estimate):
    if not estimate:
        return None
    return round((float(amount) - float(estimate)) / float(estimate) * 100)


class QuoteForm(forms.Form):
    amount = forms.IntegerField(label=_("Ish narxi (so'm)"), min_value=1000, max_value=1_000_000_000,
                                widget=forms.NumberInput(attrs={'step': 1000, 'placeholder': '250000'}))
    plan = forms.ChoiceField(label=_("To'lov tartibi"), choices=PLAN_CHOICES, widget=forms.RadioSelect)
    note = forms.CharField(label=_('Narxga nima kiradi'), required=False, max_length=1000,
                           widget=forms.Textarea(attrs={'rows': 3, 'placeholder': _('Masalan: nasos almashtirish, '
                                                                                     'ehtiyot qism narxi bilan')}))


    def __init__(self, *args, estimate=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.estimate = estimate

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        diff = deviation_percent(amount, self.estimate) if amount else None
        if diff is not None and abs(diff) > QUOTE_DEVIATION_LIMIT and not (cleaned.get('note') or '').strip():
            self.add_error('note', _(
                "Narx katalogdagidan %(diff)s%% farq qiladi. Mijoz tushunishi uchun sababini yozing "
                "(masalan: qo'shimcha ehtiyot qism, murakkab joylashuv)."
            ) % {'diff': f'{diff:+d}'})
        return cleaned


class PasswordResetForm(forms.Form):
    """Parolni SMS orqali tiklash."""

    phone = forms.CharField(label=_('Telefon raqam'), widget=forms.TextInput(attrs={'type': 'tel', 'data-phone': ''}))
    password1 = forms.CharField(label=_('Yangi parol'), strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label=_('Parolni takrorlang'), strip=False, widget=forms.PasswordInput)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get('phone'))
        if not otp.is_verified(self.request, phone, PhoneCode.PURPOSE_RESET):
            raise forms.ValidationError(_('Telefon raqamni SMS kod bilan tasdiqlang'))
        self.user = get_user_model().objects.filter(username=phone.lstrip('+'), is_active=True).first()
        if self.user is None:
            raise forms.ValidationError(_("Bu raqam bilan ro'yxatdan o'tilmagan"))
        return phone

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', _('Parollar mos kelmadi'))
        elif p1 and self.user:
            try:
                password_validation.validate_password(p1, self.user)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data['password1'])
        self.user.save(update_fields=['password'])
        return self.user
