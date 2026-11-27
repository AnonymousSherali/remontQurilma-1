from django.core.management.base import BaseCommand

from config.roles import setup


class Command(BaseCommand):
    help = "Admin rollari (Operator, Nizo hakami, Moliyachi, Marketolog) — yaratadi yoki yangilaydi"

    def handle(self, *args, **options):
        for name, count in setup().items():
            self.stdout.write(f'{name}: {count} ta huquq')
        self.stdout.write(self.style.SUCCESS("Tayyor. Xodimga rol: Admin → Foydalanuvchilar → Guruhlar."))
