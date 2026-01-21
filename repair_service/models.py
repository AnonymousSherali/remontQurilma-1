from django.db import models
from django.utils import timezone


class ServiceRequest(models.Model):
    """Модель для заявок на ремонт"""

    STATUS_CHOICES = [
        ('new', 'Новая'),
        ('in_progress', 'В обработке'),
        ('completed', 'Завершена'),
        ('cancelled', 'Отменена'),
    ]

    # Информация о клиенте
    name = models.CharField('Имя', max_length=100)
    phone = models.CharField('Телефон', max_length=20)
    email = models.EmailField('Email', blank=True, null=True)

    # Информация о проблеме
    problem_description = models.TextField('Описание проблемы', blank=True)
    appliance_type = models.CharField('Тип техники', max_length=100, default='Стиральная машина')
    brand = models.CharField('Бренд', max_length=100, blank=True)

    # Статус заявки
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='new')

    # Системные поля
    created_at = models.DateTimeField('Дата создания', default=timezone.now)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    # Комментарии администратора
    admin_notes = models.TextField('Комментарии администратора', blank=True)

    class Meta:
        verbose_name = 'Заявка на ремонт'
        verbose_name_plural = 'Заявки на ремонт'
        ordering = ['-created_at']

    def __str__(self):
        return f"Заявка #{self.id} - {self.name} ({self.phone})"


class Service(models.Model):
    """Модель для услуг"""

    name = models.CharField('Название услуги', max_length=200)
    description = models.TextField('Описание', blank=True)
    price_from = models.DecimalField('Цена от', max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField('Активна', default=True)
    order = models.IntegerField('Порядок отображения', default=0)

    class Meta:
        verbose_name = 'Услуга'
        verbose_name_plural = 'Услуги'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Testimonial(models.Model):
    """Модель для отзывов клиентов"""

    client_name = models.CharField('Имя клиента', max_length=100)
    text = models.TextField('Текст отзыва')
    rating = models.IntegerField('Рейтинг', default=5, choices=[(i, i) for i in range(1, 6)])
    is_published = models.BooleanField('Опубликован', default=True)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Отзыв от {self.client_name} ({self.rating}/5)"


class Brand(models.Model):
    """Модель для брендов техники"""

    name = models.CharField('Название бренда', max_length=100)
    logo = models.ImageField('Логотип', upload_to='brands/', blank=True)
    is_active = models.BooleanField('Активен', default=True)
    order = models.IntegerField('Порядок отображения', default=0)

    class Meta:
        verbose_name = 'Бренд'
        verbose_name_plural = 'Бренды'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name
