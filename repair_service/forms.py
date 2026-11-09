from django import forms
from django.utils.translation import gettext_lazy as _

from masters.models import Category, Master

from .models import ServiceRequest
from .phone import normalize_phone


class ServiceRequestForm(forms.ModelForm):
    """Saytdagi barcha ariza formalari uchun yagona forma."""

    # Bot tuzog'i: odam ko'rmaydigan maydon. To'ldirilgan bo'lsa — spam.
    # Yashirin <input type=hidden> ni ko'p botlar o'tkazib yuboradi, shuning uchun
    # oddiy matn maydoni CSS bilan ekrandan tashqariga chiqariladi (.hp).
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={'tabindex': '-1', 'autocomplete': 'off'}))
    consent = forms.BooleanField(
        required=True,
        error_messages={'required': _("Shaxsiy ma'lumotlarni qayta ishlashga rozilik bering")},
    )

    class Meta:
        model = ServiceRequest
        fields = ['name', 'phone', 'email', 'address', 'category', 'master', 'problem_description', 'consent']
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

    def clean(self):
        cleaned = super().clean()
        master = cleaned.get('master')
        category = cleaned.get('category')
        if master and not master.is_available:
            self.add_error('master', _('Bu usta hozir buyurtma qabul qilmayapti. Boshqa ustani tanlang.'))
        if master and (not category or not master.categories.filter(pk=category.pk).exists()):
            # Santexnikka "elektrik" arizasi kabi mantiqsizlikning oldini olamiz:
            # yo'nalish ustaning o'z yo'nalishlaridan biriga keltiriladi.
            cleaned['category'] = master.categories.order_by('order').first()
        return cleaned
