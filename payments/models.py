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


class Payment(models.Model):
    """To'lov tizimi orqali o'tgan tranzaksiya (bitta bosqich uchun bir yoki bir necha urinish)."""

    PROVIDER_DEMO = 'demo'
    PROVIDER_PAYME = 'payme'
    PROVIDER_CHOICES = [(PROVIDER_DEMO, 'Demo'), (PROVIDER_PAYME, 'Payme')]

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

    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, related_name='payments', verbose_name='Bosqich')
    provider = models.CharField('Tizim', max_length=10, choices=PROVIDER_CHOICES)
    provider_id = models.CharField('Tizimdagi ID', max_length=64, blank=True, db_index=True)
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
        ]

    def __str__(self):
        return f'{self.get_provider_display()} {self.provider_id or self.pk}: {self.amount}'


def platform_fee_percent():
    return Decimal(str(getattr(settings, 'PLATFORM_FEE_PERCENT', 10)))
