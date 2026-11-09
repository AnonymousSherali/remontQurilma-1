from django.db import models


class PhoneCode(models.Model):
    """Telefon raqamga yuborilgan bir martalik kod.

    Kodning o'zi saqlanmaydi — faqat xeshi. Baza sizib chiqsa ham kodlar oshkor bo'lmaydi.
    """

    PURPOSE_LOGIN = 'login'          # mijoz: "Mening buyurtmalarim" va buyurtmadagi amallar
    PURPOSE_REGISTER = 'register'    # usta ro'yxatdan o'tishi
    PURPOSE_RESET = 'reset'          # usta parolini tiklash
    PURPOSE_CHOICES = [
        (PURPOSE_LOGIN, 'Kirish / amalni tasdiqlash'),
        (PURPOSE_REGISTER, "Ro'yxatdan o'tish"),
        (PURPOSE_RESET, 'Parolni tiklash'),
    ]

    phone = models.CharField('Telefon', max_length=20, db_index=True)
    purpose = models.CharField('Maqsad', max_length=20, choices=PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField('Urinishlar', default=0)
    is_used = models.BooleanField('Ishlatilgan', default=False)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField('Yuborilgan', auto_now_add=True)
    expires_at = models.DateTimeField('Amal qilish muddati')

    class Meta:
        verbose_name = 'SMS kod'
        verbose_name_plural = 'SMS kodlar'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.phone} ({self.get_purpose_display()})'
