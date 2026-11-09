"""Telegram'ga webhook manzilini ro'yxatdan o'tkazish (bir marta, saytni ishga tushirgach):

    python manage.py telegram_webhook            # SITE_URL/telegram/webhook/ ga ulaydi
    python manage.py telegram_webhook --delete   # webhook'ni o'chirish

Talab: TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET va HTTPS'dagi SITE_URL.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from telegram_bot import client


class Command(BaseCommand):
    help = "Telegram bot webhook'ini sozlaydi"

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true')

    def handle(self, *args, **options):
        if not client.enabled():
            raise CommandError('TELEGRAM_BOT_TOKEN sozlanmagan')
        if options['delete']:
            self.stdout.write(str(client.api('deleteWebhook', {})))
            return
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError('TELEGRAM_WEBHOOK_SECRET sozlanmagan (tasodifiy uzun satr yozing)')
        url = settings.SITE_URL.rstrip('/') + reverse('telegram_webhook')
        if not url.startswith('https://'):
            raise CommandError(f'Telegram faqat HTTPS manzilni qabul qiladi: {url}')
        result = client.api('setWebhook', {
            'url': url, 'secret_token': settings.TELEGRAM_WEBHOOK_SECRET,
            'allowed_updates': ['message', 'callback_query'],
        })
        client.api('setMyCommands', {'commands': [
            {'command': 'buyurtmalar', 'description': 'Faol buyurtmalar'},
            {'command': 'stop', 'description': "Xabarlarni o'chirish"},
        ]})
        self.stdout.write(self.style.SUCCESS(f'{url}: {result}'))
