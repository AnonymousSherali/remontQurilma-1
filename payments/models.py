from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .plans import PLAN_CHOICES, PLAN_ON_COMPLETION


class Quote(models.Model):
    """Usta taklif qilgan narx va to'lov rejasi. Mijoz tasdiqlagach bosqichlar yaratiladi."""

    STATUS_PROPOSED = 'proposed'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PROPOSED, _('Mijoz javobini kutmoqda')),
        (STATUS_APPROVED, _('Kelishilgan')),
        (STATUS_REJECTED, _('Rad etilgan')),
    ]

    order = models.OneToOneField(
        'repair_service.ServiceRequest', on_delete=models.CASCADE, related_name='quote', verbose_name='Buyurtma',
    )
    amount = models.DecimalField("Summa (so'm)", max_digits=12, decimal_places=0)
    plan = models.CharField("To'lov rejasi", max_length=20, choices=PLAN_CHOICES, default=PLAN_ON_COMPLETION)
    note = models.TextField("Nima kiradi (smeta)", blank=True, max_length=1000)
    status = models.CharField('Holat', max_length=10, choices=STATUS_CHOICES, default=STATUS_PROPOSED)
    proposed_at = models.DateTimeField('Taklif qilingan', default=timezone.now)
    decided_at = models.DateTimeField('Javob berilgan', null=True, blank=True)

    class Meta:
        verbose_name = 'Narx taklifi'
        verbose_name_plural = 'Narx takliflari'

    def __str__(self):
        return f'#{self.order_id}: {self.amount} so\'m'

    @property
    def is_online(self):
        return self.plan != 'cash'


class Milestone(models.Model):
    """To'lov bosqichi (eskrou).

    pending  -> mijoz hali to'lamagan
    held     -> mijoz to'lagan, pul platformada ushlab turilibdi (usta ko'radi: "kafolatlangan")
    released -> bosqich bajarildi, pul ustaga tegishli (komissiya chegirilgan holda)
    refunded -> nizo natijasida mijozga qaytarilgan
    """

    STATE_PENDING = 'pending'
    STATE_HELD = 'held'
    STATE_RELEASED = 'released'
    STATE_REFUNDED = 'refunded'
    STATE_CHOICES = [
        (STATE_PENDING, _("To'lanmagan")),
        (STATE_HELD, _('Ushlab turilibdi')),
        (STATE_RELEASED, _('Ustaga chiqarildi')),
        (STATE_REFUNDED, _('Qaytarildi')),
    ]

    order = models.ForeignKey(
        'repair_service.ServiceRequest', on_delete=models.CASCADE, related_name='milestones', verbose_name='Buyurtma',
    )
    position = models.PositiveSmallIntegerField('Tartib')
    title = models.CharField('Nomi', max_length=200)
    amount = models.DecimalField("Summa (so'm)", max_digits=12, decimal_places=0)
    release_status = models.CharField('Qaysi bosqichda chiqariladi', max_length=20)
    state = models.CharField('Holat', max_length=10, choices=STATE_CHOICES, default=STATE_PENDING)
    fee_percent = models.DecimalField('Komissiya (%)', max_digits=5, decimal_places=2, default=0)

    held_at = models.DateTimeField('To\'langan', null=True, blank=True)
    released_at = models.DateTimeField('Chiqarilgan', null=True, blank=True)
    refunded_at = models.DateTimeField('Qaytarilgan', null=True, blank=True)
    paid_out_at = models.DateTimeField('Ustaga o\'tkazilgan', null=True, blank=True,
                                       help_text="Admin ustaning kartasiga o'tkazgach belgilaydi")
    payout = models.ForeignKey('Payout', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='milestones', verbose_name="O'tkazma")
    # Promo-kod chegirmasi — platforma hisobidan: mijoz kamroq to'laydi, usta to'liq oladi
    discount = models.DecimalField("Chegirma (so'm)", max_digits=12, decimal_places=0, default=0)

    class Meta:
        verbose_name = "To'lov bosqichi"
        verbose_name_plural = "To'lov bosqichlari"
        ordering = ['order', 'position']
        unique_together = [('order', 'position')]

    def __str__(self):
        return f'#{self.order_id} · {self.position}. {self.title}'

    @property
    def fee_amount(self):
        return (self.amount * self.fee_percent / Decimal(100)).quantize(Decimal('1'))

    @property
    def master_amount(self):
        return self.amount - self.fee_amount

    @property
    def amount_due(self):
        """Mijoz to'laydigan summa (chegirma ayirilgan)."""
        return self.amount - self.discount


class Refund(models.Model):
    """Mijozga pul qaytarish (nizo qarori yoki admin amali). payments/refunds.py."""

    STATUS_PENDING, STATUS_DONE, STATUS_FAILED = 'pending', 'done', 'failed'
    STATUS_CHOICES = [(STATUS_PENDING, 'Qaytarilishi kerak'), (STATUS_DONE, 'Qaytarildi'),
                      (STATUS_FAILED, 'Avtomatik qaytarilmadi — qo\'lda')]
    METHOD_AUTO, METHOD_PROVIDER, METHOD_MANUAL = 'auto', 'provider', 'manual'
    METHOD_CHOICES = [(METHOD_AUTO, "API orqali avtomatik"), (METHOD_PROVIDER, "To'lov tizimi kabinetidan bekor qilindi"),
                      (METHOD_MANUAL, "Qo'lda belgilandi")]

    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, related_name='refunds', verbose_name='Bosqich')
    payment = models.ForeignKey('Payment', on_delete=models.PROTECT, null=True, blank=True, related_name='refunds',
                                verbose_name="Asl to'lov")
    amount = models.DecimalField("Summa (so'm)", max_digits=12, decimal_places=0)
    status = models.CharField('Holat', max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    method = models.CharField('Qanday', max_length=10, choices=METHOD_CHOICES, blank=True)
    note = models.CharField('Izoh', max_length=500, blank=True)
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)
    done_at = models.DateTimeField('Qaytarilgan', null=True, blank=True)

    class Meta:
        verbose_name = 'Pul qaytarish'
        verbose_name_plural = 'Pul qaytarishlar'
        ordering = ['status', '-created_at']

    def __str__(self):
        return f'#{self.milestone.order_id} · {self.amount}'


class PromoCode(models.Model):
    """Promo-kod: aksiya (admin yaratadi), mijozning referal kodi yoki referal mukofoti."""

    KIND_PERCENT, KIND_FIXED = 'percent', 'fixed'
    KIND_CHOICES = [(KIND_PERCENT, _('Foiz')), (KIND_FIXED, _("Qat'iy summa"))]
    PURPOSE_PROMO, PURPOSE_REFERRAL, PURPOSE_REWARD = 'promo', 'referral', 'reward'
    PURPOSE_CHOICES = [(PURPOSE_PROMO, _('Aksiya')), (PURPOSE_REFERRAL, _('Referal (do\'stga)')),
                       (PURPOSE_REWARD, _('Referal mukofoti'))]

    code = models.CharField('Kod', max_length=32, unique=True, help_text="Katta harflar bilan saqlanadi")
    purpose = models.CharField('Turi', max_length=10, choices=PURPOSE_CHOICES, default=PURPOSE_PROMO)
    kind = models.CharField('Chegirma turi', max_length=10, choices=KIND_CHOICES, default=KIND_PERCENT)
    value = models.DecimalField('Qiymati', max_digits=12, decimal_places=0,
                                help_text="Foiz (masalan 10) yoki so'm (masalan 20000)")
    max_discount = models.DecimalField("Eng ko'p chegirma (so'm)", max_digits=12, decimal_places=0,
                                       null=True, blank=True)
    min_amount = models.DecimalField("Eng kam buyurtma summasi (so'm)", max_digits=12, decimal_places=0, default=0)
    first_order_only = models.BooleanField('Faqat birinchi buyurtma', default=False)
    max_uses = models.PositiveIntegerField('Jami foydalanish chegarasi', null=True, blank=True,
                                           help_text="Bo'sh — cheklanmagan")
    per_phone_limit = models.PositiveSmallIntegerField('Bitta raqamga', default=1)
    owner_phone = models.CharField('Egasi (referal)', max_length=20, blank=True, db_index=True,
                                   help_text="Referal kodi egasi — o'z kodini ishlata olmaydi")
    only_phone = models.CharField('Faqat shu raqam uchun', max_length=20, blank=True)
    valid_from = models.DateTimeField('Boshlanishi', null=True, blank=True)
    valid_until = models.DateTimeField('Tugashi', null=True, blank=True)
    is_active = models.BooleanField('Faol', default=True)
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)

    class Meta:
        verbose_name = 'Promo-kod'
        verbose_name_plural = 'Promo-kodlar'
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class PromoRedemption(models.Model):
    """Promo-kod buyurtmaga qo'llangani. Bitta buyurtmaga — bitta kod."""

    promo = models.ForeignKey(PromoCode, on_delete=models.PROTECT, related_name='redemptions', verbose_name='Kod')
    order = models.OneToOneField('repair_service.ServiceRequest', on_delete=models.CASCADE,
                                 related_name='promo_redemption', verbose_name='Buyurtma')
    phone = models.CharField('Telefon', max_length=20, db_index=True)
    discount = models.DecimalField("Chegirma (so'm)", max_digits=12, decimal_places=0, default=0)
    rewarded = models.BooleanField('Referal mukofoti berilgan', default=False)
    created_at = models.DateTimeField('Qo\'llangan', auto_now_add=True)

    class Meta:
        verbose_name = "Promo-kod qo'llanishi"
        verbose_name_plural = "Promo-kod qo'llanishlari"

    def __str__(self):
        return f'{self.promo} → #{self.order_id}'


class Payout(models.Model):
    """Ustaga bitta o'tkazma: bir nechta chiqarilgan bosqich summasi (komissiyasiz).

    Pulni administrator bank/to'lov tizimi orqali qo'lda o'tkazadi; bu yozuv — hisobot
    (payments/payouts.py).
    """

    master = models.ForeignKey('masters.Master', on_delete=models.PROTECT, related_name='payouts',
                               verbose_name='Usta')
    amount = models.DecimalField("Ustaga o'tkazilgan (so'm)", max_digits=12, decimal_places=0)
    gross = models.DecimalField("Mijozlar to'lagan (so'm)", max_digits=12, decimal_places=0)
    fee = models.DecimalField("Komissiya (so'm)", max_digits=12, decimal_places=0)
    count = models.PositiveIntegerField('Bosqichlar soni')
    card = models.CharField('Karta raqami', max_length=16, blank=True)
    holder = models.CharField('Karta egasi', max_length=100, blank=True)
    note = models.CharField('Izoh', max_length=255, blank=True)
    STATUS_PREPARED, STATUS_PAID, STATUS_FAILED = 'prepared', 'paid', 'failed'
    STATUS_CHOICES = [(STATUS_PREPARED, "Tayyorlangan — o'tkazilishi kerak"), (STATUS_PAID, "O'tkazildi"),
                      (STATUS_FAILED, "O'tkazilmadi")]
    status = models.CharField('Holat', max_length=10, choices=STATUS_CHOICES, default=STATUS_PAID)
    provider = models.CharField("Qanday o'tkazildi", max_length=20, default='manual')
    provider_ref = models.CharField("To'lov tizimidagi raqam", max_length=64, blank=True)
    paid_at = models.DateTimeField("O'tkazilgan", null=True, blank=True)
    created_at = models.DateTimeField("Yaratilgan", default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name='Kim belgiladi')

    class Meta:
        verbose_name = "Ustaga o'tkazma"
        verbose_name_plural = "Ustalarga o'tkazmalar"
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.master} · {self.amount} so\'m · {self.created_at:%d.%m.%Y}'


class Purchase(models.Model):
    """Ustaning tarif xaridi: TOP (qidiruvda yuqorida) yoki PRO (kam komissiya va boshqa afzalliklar).

    To'lov buyurtma bosqichlari bilan bir xil tizimlar orqali (Payme/Click/Uzum) o'tadi;
    to'langach payments.tariffs.activate() muddatni uzaytiradi.
    """

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, _("To'lov kutilmoqda")),
        (STATUS_PAID, _("To'langan")),
        (STATUS_CANCELLED, _('Bekor qilingan')),
    ]

    master = models.ForeignKey('masters.Master', on_delete=models.CASCADE, related_name='purchases', verbose_name='Usta')
    plan = models.CharField('Tarif', max_length=20)
    kind = models.CharField('Turi', max_length=10)  # top | pro
    days = models.PositiveSmallIntegerField('Kunlar')
    amount = models.DecimalField("Summa (so'm)", max_digits=12, decimal_places=0)
    status = models.CharField('Holat', max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)
    paid_at = models.DateTimeField("To'langan", null=True, blank=True)

    class Meta:
        verbose_name = 'Tarif xaridi'
        verbose_name_plural = 'Tarif xaridlari'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.master} · {self.plan} · {self.amount}'


class Payment(models.Model):
    """To'lov tizimi orqali o'tgan tranzaksiya (bitta bosqich uchun bir yoki bir necha urinish)."""

    PROVIDER_DEMO = 'demo'
    PROVIDER_PAYME = 'payme'
    PROVIDER_CLICK = 'click'
    PROVIDER_UZUM = 'uzum'
    PROVIDER_CHOICES = [(PROVIDER_DEMO, 'Demo'), (PROVIDER_PAYME, 'Payme'), (PROVIDER_CLICK, 'Click'),
                        (PROVIDER_UZUM, 'Uzum Bank')]

    # Payme holat kodlari bilan mos: 1 yaratilgan, 2 bajarilgan, -1/-2 bekor qilingan
    STATE_CREATED = 1
    STATE_PERFORMED = 2
    STATE_CANCELLED = -1
    STATE_CANCELLED_AFTER_PERFORM = -2
    STATE_CHOICES = [
        (STATE_CREATED, 'Yaratilgan'),
        (STATE_PERFORMED, "To'langan"),
        (STATE_CANCELLED, 'Bekor qilingan'),
        (STATE_CANCELLED_AFTER_PERFORM, "To'lovdan keyin bekor qilingan"),
    ]

    # To'lov yo buyurtma bosqichi, yo tarif xaridi uchun (payments/payables.py)
    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, related_name='payments', verbose_name='Bosqich',
                                  null=True, blank=True)
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name='payments',
                                 verbose_name='Tarif xaridi', null=True, blank=True)
    provider = models.CharField('Tizim', max_length=10, choices=PROVIDER_CHOICES)
    provider_id = models.CharField('Tizimdagi ID', max_length=64, blank=True, db_index=True)
    provider_doc_id = models.CharField("Tizimdagi hujjat raqami", max_length=64, blank=True,
                                       help_text="Click: click_paydoc_id (kabinetda qidirish uchun)")
    amount = models.DecimalField("Summa (so'm)", max_digits=12, decimal_places=0)
    state = models.SmallIntegerField('Holat', choices=STATE_CHOICES, default=STATE_CREATED)
    reason = models.SmallIntegerField('Bekor qilish sababi', null=True, blank=True)
    provider_time = models.BigIntegerField('Tizim vaqti (ms)', null=True, blank=True)
    created_at = models.DateTimeField('Yaratilgan', auto_now_add=True)
    performed_at = models.DateTimeField("To'langan", null=True, blank=True)
    cancelled_at = models.DateTimeField('Bekor qilingan', null=True, blank=True)

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'provider_id'], condition=~models.Q(provider_id=''),
                                    name='unique_provider_transaction'),
            models.CheckConstraint(
                condition=models.Q(milestone__isnull=False, purchase__isnull=True)
                | models.Q(milestone__isnull=True, purchase__isnull=False),
                name='payment_exactly_one_target',
            ),
        ]

    def __str__(self):
        return f'{self.get_provider_display()} {self.provider_id or self.pk}: {self.amount}'


def platform_fee_percent():
    return Decimal(str(getattr(settings, 'PLATFORM_FEE_PERCENT', 10)))
