from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Master, Review


@receiver(post_save, sender=Review)
@receiver(post_delete, sender=Review)
def update_master_rating(sender, instance, **kwargs):
    try:
        master = Master.objects.get(pk=instance.master_id)
    except Master.DoesNotExist:  # usta o'zi o'chirilayotgan bo'lsa
        return
    master.recalculate_rating()
