from django.apps import AppConfig


class RepairServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'repair_service'
    verbose_name = 'Arizalar va sayt kontenti'

    def ready(self):
        from . import signals  # noqa: F401  rasm o'chganda faylini ham o'chirish
