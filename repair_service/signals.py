from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import OrderPhoto


@receiver(post_delete, sender=OrderPhoto)
def delete_photo_files(sender, instance, **kwargs):
    """Rasm yozuvi o'chganda fayllarini ham o'chiramiz.

    Signal — modelning delete() metodidan ishonchliroq: buyurtma o'chirilganda rasmlar
    kaskad bilan ommaviy o'chiriladi va delete() chaqirilmaydi, fayllar diskda qolib ketardi.
    """
    for field in (instance.image, instance.thumbnail):
        if field:
            field.delete(save=False)
