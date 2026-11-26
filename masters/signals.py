from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Master, MasterDocument, Review


@receiver(post_save, sender=Review)
@receiver(post_delete, sender=Review)
def update_master_rating(sender, instance, **kwargs):
    try:
        master = Master.objects.get(pk=instance.master_id)
    except Master.DoesNotExist:  # usta o'zi o'chirilayotgan bo'lsa
        return
    master.recalculate_rating()


@receiver(post_delete, sender=MasterDocument)
def delete_document_file(sender, instance, **kwargs):
    """Hujjat yozuvi o'chsa (usta o'chirilganda kaskad bilan ham) — faylini ham o'chiramiz."""
    if instance.file:
        instance.file.delete(save=False)


@receiver(post_save, sender=Master)
def welcome_bonus(sender, instance, **kwargs):
    """Birinchi tasdiqlanganda bepul TOP (admin amali, hujjat tasdig'i yoki forma — qaysi yo'l bo'lmasin)."""
    if instance.is_verified and not instance.welcome_bonus_given:
        from .onboarding import grant_welcome_bonus
        transaction.on_commit(lambda: grant_welcome_bonus(Master.objects.get(pk=instance.pk)))
