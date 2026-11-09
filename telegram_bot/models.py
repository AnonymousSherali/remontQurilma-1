import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone

LINK_TTL = timedelta(minutes=30)


class LinkCode(models.Model):
    """Ustaning akkauntini Telegram chatga ulash uchun bir martalik kod.

    Usta kabinetda "Telegram'ni ulash" ni bosadi -> t.me/BOT?start=m<kod> ochiladi.
    Kod 30 daqiqa amal qiladi va bir marta ishlatiladi.
    """

    master = models.ForeignKey('masters.Master', on_delete=models.CASCADE, related_name='telegram_codes')
    code = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Telegram ulash kodi'
        verbose_name_plural = 'Telegram ulash kodlari'

    @classmethod
    def issue(cls, master):
        cls.objects.filter(master=master, used_at__isnull=True).delete()
        return cls.objects.create(master=master, code=secrets.token_hex(12))

    @property
    def is_valid(self):
        return self.used_at is None and timezone.now() - self.created_at < LINK_TTL
