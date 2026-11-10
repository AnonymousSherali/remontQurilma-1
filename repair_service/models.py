import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ServiceRequest(models.Model):
    """Mijoz arizasi. Aniq ustaga yoki umumiy (admin usta biriktiradi)."""

    # Bosqichlar ketma-ketligi va kim o'zgartirishi — repair_service/workflow.py da.
    STATUS_NEW = 'new'                  # 01 Buyurtmachi: yaratildi
    STATUS_ACCEPTED = 'accepted'        # 02 Usta: qabul qildi
    STATUS_ARRIVED = 'arrived'          # 03 Usta: joyida
    STATUS_IN_PROGRESS = 'in_progress'  # 04 Usta: ishda
    STATUS_COMPLETED = 'completed'      # 05 Usta: bajarildi
    STATUS_CONFIRMED = 'confirmed'      # 06 Buyurtmachi: tasdiqladi
    STATUS_CANCELLED = 'cancelled'
    STATUS_DISPUTED = 'disputed'

    STATUS_CHOICES = [
        (STATUS_NEW, _('Yaratildi')),
        (STATUS_ACCEPTED, _('Qabul qilindi')),
        (STATUS_ARRIVED, _('Joyida')),
        (STATUS_IN_PROGRESS, _('Ishda')),
        (STATUS_COMPLETED, _('Bajarildi')),
        (STATUS_CONFIRMED, _('Tasdiqlandi')),
        (STATUS_CANCELLED, _('Bekor qilindi')),
        (STATUS_DISPUTED, _('Nizo')),
    ]
    # Asosiy oqim tartibi (timeline'dagi 01–06)
    FLOW = [STATUS_NEW, STATUS_ACCEPTED, STATUS_ARRIVED, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_CONFIRMED]
    OPEN_STATUSES = (STATUS_NEW, STATUS_ACCEPTED, STATUS_ARRIVED, STATUS_IN_PROGRESS, STATUS_COMPLETED)

    # Mijoz haqida ma'lumot
    name = models.CharField('Ism', max_length=100)
    phone = models.CharField('Telefon', max_length=20)
    email = models.EmailField('Email', blank=True, null=True)
    address = models.CharField('Manzil', max_length=255, blank=True)
    # Taxminiy joylashuv (GPS yoki tuman markazi) — ochiq buyurtmalar lentasida ustaga masofani
    # ko'rsatish uchun. Aniq manzil ustaga faqat buyurtmani olgandan keyin ko'rinadi.
    district = models.CharField('Tuman', max_length=40, blank=True)
    latitude = models.DecimalField('Kenglik', max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField('Uzunlik', max_digits=9, decimal_places=6, null=True, blank=True)

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
    # Mijoz katalogdan tanlagan xizmat — taxminiy narx shundan hisoblanadi
    catalog_item = models.ForeignKey(
        'Service', on_delete=models.SET_NULL, null=True, blank=True, related_name='requests',
        verbose_name='Katalogdagi xizmat',
    )
    quantity = models.PositiveSmallIntegerField('Miqdori', default=1)
    appliance_type = models.CharField('Texnika turi', max_length=100, blank=True)
    brand = models.CharField('Brend', max_length=100, blank=True)

    # Ariza holati
    status = models.CharField('Holat', max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

    # Shaxsga doir ma'lumotlarni qayta ishlashga rozilik (qonun talabi)
    consent = models.BooleanField("Ma'lumotlarni qayta ishlashga rozilik", default=False)

    # SMS orqali yuboriladigan buyurtma sahifasi tilini eslab qolamiz
    language = models.CharField('Til', max_length=5, default='uz')
    # Tasdiqlangan buyurtma rasmlari usta portfoliosida ko'rinishi mumkinmi (mijoz o'chira oladi)
    photos_in_portfolio = models.BooleanField('Rasmlar portfolioda', default=True)
    # Lentaga qayta tushgan vaqt (usta voz kechganda). Bo'sh bo'lsa — yaratilgan vaqt hisoblanadi.
    open_since = models.DateTimeField('Lentada (qachondan)', null=True, blank=True)
    # Buyurtmadan voz kechgan ustalar — lentada ularga qayta ko'rsatilmaydi
    declined_by = models.ManyToManyField('masters.Master', blank=True, related_name='declined_orders',
                                         verbose_name='Voz kechgan ustalar')
    # Mijoz "Telegram'da kuzatish" ni bosgan bo'lsa — xabarlar SMS o'rniga Telegram'ga (bepul)
    telegram_chat_id = models.BigIntegerField('Mijoz Telegram chati', null=True, blank=True, db_index=True)

    # Mijozning maxfiy havolasi: /buyurtma/<kalit>/ (kuzatish) va /baho/<kalit>/
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

    @property
    def catalog_estimate(self):
        """Katalog bo'yicha taxminiy narx (tanlanmagan bo'lsa None)."""
        if self.catalog_item_id is None or self.catalog_item.is_free:
            return None
        return self.catalog_item.estimate(self.quantity)

    def reached(self, status):
        """Buyurtma shu bosqichga yetganmi (yoki undan o'tganmi)."""
        if self.status not in self.FLOW or status not in self.FLOW:
            return False
        return self.FLOW.index(self.status) >= self.FLOW.index(status)

    def get_review_url(self):
        return reverse('masters:review', args=[self.review_token])

    def get_customer_url(self):
        return reverse('repair_service:order', args=[self.review_token])

    def get_master_url(self):
        return reverse('masters:order', args=[self.pk])

    @property
    def can_be_reviewed(self):
        """Baho: usta "Bajarildi" deganidan keyin (tasdiqlash bilan birga) yoki tasdiqlangach."""
        return (
            self.status in (self.STATUS_COMPLETED, self.STATUS_CONFIRMED)
            and self.master_id is not None
            and not hasattr(self, 'review')
        )


class OrderEvent(models.Model):
    """Buyurtma tarixidagi har bir qadam: kim, qachon, nima qildi.

    Timeline'dagi vaqtlar shu yerdan olinadi; nizolarda dalil bo'lib xizmat qiladi.
    """

    ACTOR_CUSTOMER = 'customer'
    ACTOR_MASTER = 'master'
    ACTOR_ADMIN = 'admin'
    ACTOR_SYSTEM = 'system'
    ACTOR_CHOICES = [
        (ACTOR_CUSTOMER, _('Buyurtmachi')),
        (ACTOR_MASTER, _('Usta')),
        (ACTOR_ADMIN, _('Administrator')),
        (ACTOR_SYSTEM, _('Tizim')),
    ]

    order = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='events', verbose_name='Buyurtma')
    status = models.CharField('Holat', max_length=20, choices=ServiceRequest.STATUS_CHOICES)
    actor = models.CharField('Kim', max_length=10, choices=ACTOR_CHOICES)
    note = models.CharField('Izoh', max_length=500, blank=True)
    created_at = models.DateTimeField('Vaqt', default=timezone.now)

    class Meta:
        verbose_name = 'Buyurtma tarixi'
        verbose_name_plural = 'Buyurtma tarixi'
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'#{self.order_id} {self.get_status_display()} ({self.get_actor_display()})'


def _photo_path(instance, filename):
    # Tasodifiy nom: rasm manzilini taxmin qilib bo'lmasin
    return f'orders/{instance.order_id}/{uuid.uuid4().hex}.jpg'


def _thumb_path(instance, filename):
    return f'orders/{instance.order_id}/thumb_{uuid.uuid4().hex}.jpg'


class OrderPhoto(models.Model):
    """Buyurtma rasmi: mijozning muammo rasmi yoki ustaning "oldin/keyin" rasmlari.

    Yuklashda EXIF (GPS joylashuv, telefon modeli) o'chiriladi — repair_service/photos.py.
    """

    KIND_PROBLEM = 'problem'
    KIND_BEFORE = 'before'
    KIND_AFTER = 'after'
    KIND_CHOICES = [
        (KIND_PROBLEM, _('Muammo')),
        (KIND_BEFORE, _('Oldin')),
        (KIND_AFTER, _('Keyin')),
    ]

    order = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='photos', verbose_name='Buyurtma')
    kind = models.CharField('Turi', max_length=10, choices=KIND_CHOICES)
    uploaded_by = models.CharField('Kim yukladi', max_length=10, choices=OrderEvent.ACTOR_CHOICES)
    image = models.ImageField('Rasm', upload_to=_photo_path)
    thumbnail = models.ImageField('Kichik nusxa', upload_to=_thumb_path, blank=True)
    caption = models.CharField('Izoh', max_length=200, blank=True)
    is_hidden = models.BooleanField(
        'Portfoliodan yashirilgan', default=False,
        help_text="Admin moderatsiyasi: nomaqbul rasm portfolioda ko'rinmaydi (buyurtmada qoladi)",
    )
    created_at = models.DateTimeField('Yuklangan', auto_now_add=True)

    class Meta:
        verbose_name = 'Buyurtma rasmi'
        verbose_name_plural = 'Buyurtma rasmlari'
        ordering = ['created_at']

    def __str__(self):
        return f'#{self.order_id} {self.get_kind_display()}'



class Service(models.Model):
    """Narxlar katalogidagi xizmat: "Kran almashtirish — 80 000 so'm".

    Platforma narxi — mijoz oldindan biladi. Usta joyida boshqa narx aytishi
    mumkin, lekin katalogdan 20% dan ko'p farq qilsa sababini yozishi shart va
    mijoz farqni ko'radi (payments.forms / QuoteForm).
    """

    PRICE_FIXED = 'fixed'
    PRICE_FROM = 'from'
    PRICE_TYPE_CHOICES = [
        (PRICE_FIXED, _("Qat'iy narx")),
        (PRICE_FROM, _('...dan (minimal narx)')),
    ]

    UNIT_SERVICE = 'service'
    UNIT_CHOICES = [
        (UNIT_SERVICE, _('xizmat')),
        ('piece', _('dona')),
        ('meter', _('metr')),
        ('sqm', _('m²')),
        ('point', _('nuqta')),
        ('hour', _('soat')),
    ]

    category = models.ForeignKey(
        'masters.Category', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='services', verbose_name="Yo'nalish",
    )
    name = models.CharField('Xizmat nomi', max_length=200)
    name_ru = models.CharField('Xizmat nomi (ruscha)', max_length=200, blank=True)
    description = models.TextField('Tavsif', blank=True)
    description_ru = models.TextField('Tavsif (ruscha)', blank=True)
    includes = models.TextField(
        'Narxga nima kiradi', blank=True,
        help_text="Har bir qator — alohida band. Masalan: «Eski kranni yechish», «Germetik»",
    )
    includes_ru = models.TextField('Narxga nima kiradi (ruscha)', blank=True)
    price_from = models.DecimalField(
        'Narx', max_digits=10, decimal_places=2, default=0,
        help_text="0 bo'lsa saytda «Bepul» deb ko'rsatiladi",
    )
    price_type = models.CharField('Narx turi', max_length=10, choices=PRICE_TYPE_CHOICES, default=PRICE_FROM)
    unit = models.CharField('Birlik', max_length=10, choices=UNIT_CHOICES, default=UNIT_SERVICE)
    duration_minutes = models.PositiveIntegerField(
        'Taxminiy vaqt (daqiqa)', null=True, blank=True, help_text="Mijozga «~1 soat» ko'rinishida chiqadi",
    )
    is_popular = models.BooleanField('Ommabop', default=False, help_text="Bosh sahifada ko'rsatiladi")
    is_active = models.BooleanField('Faol', default=True)
    order = models.IntegerField("Ko'rsatish tartibi", default=0)

    class Meta:
        verbose_name = 'Katalogdagi xizmat'
        verbose_name_plural = 'Narxlar katalogi'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    @property
    def is_free(self):
        return not self.price_from

    @property
    def is_per_unit(self):
        return self.unit != self.UNIT_SERVICE

    def includes_list(self, lang=None):
        text = self.includes_ru if (lang or '').startswith('ru') and self.includes_ru else self.includes
        return [line.strip(' •-') for line in text.splitlines() if line.strip(' •-')]

    def estimate(self, quantity=1):
        return self.price_from * max(int(quantity or 1), 1)


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
