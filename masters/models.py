from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]
RATING_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]

# Reyting bo'yicha saralashda Bayes o'rtachasi ishlatiladi: 1 ta 5★ bahosi bor
# usta 200 ta 4.8★ bahosi bor ustadan yuqori turib qolmasligi uchun.
RATING_PRIOR_MEAN = 4.0
RATING_PRIOR_WEIGHT = 3


class Category(models.Model):
    """Xizmat yo'nalishi: santexnik, elektrik, kir yuvish mashinasi ustasi..."""

    name = models.CharField('Nomi', max_length=100)
    name_ru = models.CharField('Nomi (ruscha)', max_length=100, blank=True)
    slug = models.SlugField('URL nomi', max_length=100, unique=True)
    icon = models.CharField('Belgi (emoji)', max_length=8, blank=True, default='🔧')
    description = models.CharField('Qisqa tavsif', max_length=255, blank=True)
    description_ru = models.CharField('Qisqa tavsif (ruscha)', max_length=255, blank=True)
    is_active = models.BooleanField('Faol', default=True)
    order = models.PositiveIntegerField("Ko'rsatish tartibi", default=0)

    class Meta:
        verbose_name = 'Kategoriya'
        verbose_name_plural = 'Kategoriyalar'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"{reverse('masters:list')}?category={self.slug}"


class MasterQuerySet(models.QuerySet):
    def public(self):
        """Saytda ko'rinadigan ustalar: admin tasdiqlagan va akkaunti faol."""
        return self.filter(is_verified=True, user__is_active=True)


class Master(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='master', verbose_name='Foydalanuvchi',
    )
    full_name = models.CharField('Ism familiya', max_length=150)
    phone = models.CharField('Telefon', max_length=20, unique=True)
    categories = models.ManyToManyField(Category, related_name='masters', verbose_name="Yo'nalishlar")
    experience_years = models.PositiveSmallIntegerField(
        'Tajriba (yil)', default=0, validators=[MaxValueValidator(60)],
    )
    bio = models.TextField("O'zi haqida", blank=True, max_length=1500)
    photo = models.ImageField('Rasm', upload_to='masters/', blank=True)

    address = models.CharField(
        'Hudud', max_length=255, blank=True,
        help_text="Saytda ko'rinadi. Aniq uy manzilini yozmang — tuman yoki mahalla yetarli.",
    )
    latitude = models.DecimalField('Kenglik', max_digits=9, decimal_places=6)
    longitude = models.DecimalField('Uzunlik', max_digits=9, decimal_places=6)
    service_radius_km = models.PositiveSmallIntegerField(
        'Xizmat radiusi (km)', default=10,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )

    is_verified = models.BooleanField(
        'Tasdiqlangan', default=False,
        help_text="Faqat tasdiqlangan ustalar saytda ko'rinadi. Shaxsini tekshirgandan keyin belgilang.",
    )
    is_available = models.BooleanField('Buyurtma qabul qiladi', default=True)
    # Pullik tariflar (payments/tariffs.py). Muddat o'tgach o'zi o'chadi.
    promoted_until = models.DateTimeField('TOP muddati', null=True, blank=True)
    pro_until = models.DateTimeField('PRO muddati', null=True, blank=True)
    telegram_chat_id = models.BigIntegerField('Telegram chat', null=True, blank=True, unique=True,
                                              help_text='Usta botga ulanganda avtomatik yoziladi')

    # Tez saralash uchun saqlab qo'yilgan qiymatlar. Baho qo'shilsa/o'chirilsa
    # signals.py orqali avtomatik yangilanadi.
    rating_avg = models.DecimalField('O\'rtacha baho', max_digits=3, decimal_places=2, default=0)
    reviews_count = models.PositiveIntegerField('Baholar soni', default=0)

    created_at = models.DateTimeField("Ro'yxatdan o'tgan", auto_now_add=True)
    updated_at = models.DateTimeField('Yangilangan', auto_now=True)

    objects = MasterQuerySet.as_manager()

    class Meta:
        verbose_name = 'Usta'
        verbose_name_plural = 'Ustalar'
        ordering = ['-rating_avg', 'full_name']
        indexes = [models.Index(fields=['latitude', 'longitude'])]

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse('masters:detail', args=[self.pk])

    @property
    def is_promoted(self):
        return bool(self.promoted_until and self.promoted_until > timezone.now())

    @property
    def is_pro(self):
        return bool(self.pro_until and self.pro_until > timezone.now())

    @property
    def initials(self):
        parts = [p for p in self.full_name.split() if p]
        return ''.join(p[0] for p in parts[:2]).upper() or '?'

    # Ustaning aniq uy joylashuvi oshkor bo'lmasligi uchun xaritada ~1 km
    # aniqlikkacha yaxlitlangan koordinata ko'rsatiladi.
    @property
    def public_latitude(self):
        return round(float(self.latitude), 2)

    @property
    def public_longitude(self):
        return round(float(self.longitude), 2)

    @property
    def ranking_score(self):
        n = self.reviews_count
        avg = float(self.rating_avg)
        return (RATING_PRIOR_WEIGHT * RATING_PRIOR_MEAN + n * avg) / (RATING_PRIOR_WEIGHT + n)

    def recalculate_rating(self):
        stats = self.reviews.filter(is_published=True).aggregate(
            n=Count('id'),
            q=Avg('quality'), p=Avg('punctuality'), pr=Avg('price'), po=Avg('politeness'),
        )
        n = stats['n'] or 0
        if n:
            avg = (stats['q'] + stats['p'] + stats['pr'] + stats['po']) / 4
            self.rating_avg = Decimal(str(round(avg, 2)))
        else:
            self.rating_avg = Decimal('0')
        self.reviews_count = n
        self.save(update_fields=['rating_avg', 'reviews_count'])

    def criteria_breakdown(self):
        """Mezonlar bo'yicha o'rtacha baholar (profil sahifasi uchun)."""
        stats = self.reviews.filter(is_published=True).aggregate(
            quality=Avg('quality'), punctuality=Avg('punctuality'),
            price=Avg('price'), politeness=Avg('politeness'),
        )
        return [
            (label, round(stats[key], 1) if stats[key] is not None else None)
            for key, label in Review.CRITERIA
        ]


class Review(models.Model):
    """Mijoz bahosi. Faqat bajarilgan ariza orqali qoldiriladi — soxta baholarning oldi olinadi."""

    CRITERIA = [
        ('quality', _('Ish sifati')),
        ('punctuality', _("O'z vaqtida kelishi")),
        ('price', _('Narx adolatliligi')),
        ('politeness', _('Muomala madaniyati')),
    ]

    master = models.ForeignKey(Master, on_delete=models.CASCADE, related_name='reviews', verbose_name='Usta')
    service_request = models.OneToOneField(
        'repair_service.ServiceRequest', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='review', verbose_name='Ariza',
    )
    author_name = models.CharField('Mijoz ismi', max_length=100)

    quality = models.PositiveSmallIntegerField('Ish sifati', choices=RATING_CHOICES, validators=RATING_VALIDATORS)
    punctuality = models.PositiveSmallIntegerField(
        "O'z vaqtida kelishi", choices=RATING_CHOICES, validators=RATING_VALIDATORS,
    )
    price = models.PositiveSmallIntegerField('Narx adolatliligi', choices=RATING_CHOICES, validators=RATING_VALIDATORS)
    politeness = models.PositiveSmallIntegerField(
        'Muomala madaniyati', choices=RATING_CHOICES, validators=RATING_VALIDATORS,
    )
    comment = models.TextField('Izoh', blank=True, max_length=2000)

    is_published = models.BooleanField('Nashr qilingan', default=True)
    created_at = models.DateTimeField('Sana', auto_now_add=True)

    class Meta:
        verbose_name = 'Baho'
        verbose_name_plural = 'Baholar'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author_name} → {self.master} ({self.overall})'

    @property
    def overall(self):
        values = [self.quality, self.punctuality, self.price, self.politeness]
        if any(v is None for v in values):
            return None
        return round(sum(values) / 4, 1)
