from django.db import models
from django.utils import timezone


class ServiceRequest(models.Model):
    """Ta'mirlash uchun arizalar modeli"""

    STATUS_CHOICES = [
        ('new', 'Yangi'),
        ('in_progress', 'Jarayonda'),
        ('completed', 'Yakunlandi'),
        ('cancelled', 'Bekor qilindi'),
    ]

    # Mijoz haqida ma'lumot
    name = models.CharField('Ism', max_length=100)
    phone = models.CharField('Telefon', max_length=20)
    email = models.EmailField('Email', blank=True, null=True)

    # Muammo haqida ma'lumot
    problem_description = models.TextField('Muammo tavsifi', blank=True)
    appliance_type = models.CharField('Texnika turi', max_length=100, default='Kir yuvish mashinasi')
    brand = models.CharField('Brend', max_length=100, blank=True)

    # Ariza holati
    status = models.CharField('Holat', max_length=20, choices=STATUS_CHOICES, default='new')

    # Tizim maydonlari
    created_at = models.DateTimeField('Yaratilgan sana', default=timezone.now)
    updated_at = models.DateTimeField('Yangilangan sana', auto_now=True)

    # Administrator izohlari
    admin_notes = models.TextField('Administrator izohlari', blank=True)

    class Meta:
        verbose_name = 'Ta\'mirlash arizasi'
        verbose_name_plural = 'Ta\'mirlash arizalari'
        ordering = ['-created_at']

    def __str__(self):
        return f"Ariza #{self.id} - {self.name} ({self.phone})"


class Service(models.Model):
    """Xizmatlar modeli"""

    name = models.CharField('Xizmat nomi', max_length=200)
    description = models.TextField('Tavsif', blank=True)
    price_from = models.DecimalField('Narx (dan)', max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField('Faol', default=True)
    order = models.IntegerField('Ko\'rsatish tartibi', default=0)

    class Meta:
        verbose_name = 'Xizmat'
        verbose_name_plural = 'Xizmatlar'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Testimonial(models.Model):
    """Mijozlar sharhlari modeli"""

    client_name = models.CharField('Mijoz ismi', max_length=100)
    text = models.TextField('Sharh matni')
    rating = models.IntegerField('Reyting', default=5, choices=[(i, i) for i in range(1, 6)])
    is_published = models.BooleanField('Nashr qilingan', default=True)
    created_at = models.DateTimeField('Yaratilgan sana', default=timezone.now)

    class Meta:
        verbose_name = 'Sharh'
        verbose_name_plural = 'Sharhlar'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client_name}dan sharh ({self.rating}/5)"


class Brand(models.Model):
    """Texnika brendlari modeli"""

    name = models.CharField('Brend nomi', max_length=100)
    logo = models.ImageField('Logo', upload_to='brands/', blank=True)
    is_active = models.BooleanField('Faol', default=True)
    order = models.IntegerField('Ko\'rsatish tartibi', default=0)

    class Meta:
        verbose_name = 'Brend'
        verbose_name_plural = 'Brendlar'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name
