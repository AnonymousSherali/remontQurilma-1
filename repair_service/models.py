import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone


class ServiceRequest(models.Model):
    """Mijoz arizasi. Aniq ustaga yoki umumiy (admin usta biriktiradi)."""

    STATUS_NEW = 'new'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_NEW, 'Yangi'),
        (STATUS_IN_PROGRESS, 'Jarayonda'),
        (STATUS_COMPLETED, 'Yakunlandi'),
        (STATUS_CANCELLED, 'Bekor qilindi'),
    ]

    # Mijoz haqida ma'lumot
    name = models.CharField('Ism', max_length=100)
    phone = models.CharField('Telefon', max_length=20)
    email = models.EmailField('Email', blank=True, null=True)
    address = models.CharField('Manzil', max_length=255, blank=True)

    # Muammo haqida ma'lumot
    category = models.ForeignKey(
        'masters.Category', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='requests', verbose_name="Yo'nalish",
    )
    master = models.ForeignKey(
        'masters.Master', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='requests', verbose_name='Usta',
    )
    problem_description = models.TextField('Muammo tavsifi', blank=True)
    appliance_type = models.CharField('Texnika turi', max_length=100, blank=True)
    brand = models.CharField('Brend', max_length=100, blank=True)

    # Ariza holati
    status = models.CharField('Holat', max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

    # Shaxsga doir ma'lumotlarni qayta ishlashga rozilik (qonun talabi)
    consent = models.BooleanField("Ma'lumotlarni qayta ishlashga rozilik", default=False)

    # Mijozga yuboriladigan baho havolasi uchun maxfiy kalit
    review_token = models.UUIDField('Baho kaliti', default=uuid.uuid4, unique=True, editable=False)

    # Tizim maydonlari
    created_at = models.DateTimeField('Yaratilgan sana', default=timezone.now)
    updated_at = models.DateTimeField('Yangilangan sana', auto_now=True)

    # Administrator izohlari
    admin_notes = models.TextField('Administrator izohlari', blank=True)

    class Meta:
        verbose_name = "Ta'mirlash arizasi"
        verbose_name_plural = "Ta'mirlash arizalari"
        ordering = ['-created_at']

    def __str__(self):
        return f"Ariza #{self.id} - {self.name} ({self.phone})"

    def get_review_url(self):
        return reverse('masters:review', args=[self.review_token])

    @property
    def can_be_reviewed(self):
        return (
            self.status == self.STATUS_COMPLETED
            and self.master_id is not None
            and not hasattr(self, 'review')
        )


class Service(models.Model):
    """Narxlar ro'yxatidagi xizmat"""

    category = models.ForeignKey(
        'masters.Category', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='services', verbose_name="Yo'nalish",
    )
    name = models.CharField('Xizmat nomi', max_length=200)
    description = models.TextField('Tavsif', blank=True)
    price_from = models.DecimalField(
        'Narx (dan)', max_digits=10, decimal_places=2, default=0,
        help_text="0 bo'lsa saytda «Bepul» deb ko'rsatiladi",
    )
    is_active = models.BooleanField('Faol', default=True)
    order = models.IntegerField("Ko'rsatish tartibi", default=0)

    class Meta:
        verbose_name = 'Xizmat narxi'
        verbose_name_plural = 'Xizmatlar narxi'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Testimonial(models.Model):
    """Admin qo'lda kiritadigan sharhlar.

    Diqqat: bular tekshirilmagan. Saytda faqat ustalar uchun haqiqiy baholar
    (masters.Review) bo'lmaganda zaxira sifatida ko'rsatiladi.
    """

    client_name = models.CharField('Mijoz ismi', max_length=100)
    text = models.TextField('Sharh matni')
    rating = models.IntegerField('Reyting', default=5, choices=[(i, i) for i in range(1, 6)])
    is_published = models.BooleanField('Nashr qilingan', default=True)
    created_at = models.DateTimeField('Yaratilgan sana', default=timezone.now)

    class Meta:
        verbose_name = 'Sharh (qo\'lda)'
        verbose_name_plural = "Sharhlar (qo'lda)"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client_name}dan sharh ({self.rating}/5)"


class Brand(models.Model):
    """Texnika brendlari modeli"""

    name = models.CharField('Brend nomi', max_length=100)
    logo = models.ImageField('Logo', upload_to='brands/', blank=True)
    is_active = models.BooleanField('Faol', default=True)
    order = models.IntegerField("Ko'rsatish tartibi", default=0)

    class Meta:
        verbose_name = 'Brend'
        verbose_name_plural = 'Brendlar'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name
