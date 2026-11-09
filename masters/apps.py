from django.apps import AppConfig


class MastersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'masters'
    verbose_name = 'Ustalar'

    def ready(self):
        from . import signals  # noqa: F401  baho o'zgarsa reytingni qayta hisoblash
