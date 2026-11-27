"""Ishga tushirishdan oldingi yakuniy tekshiruv — bitta buyruq:

    python manage.py launch_check          # hammasi
    python manage.py launch_check --live   # + Eskiz, Telegram va SITE_URL ga haqiqiy so'rov

1) Xavfsizlik va sozlamalar (check --deploy, shu jumladan techservice.W001…W008)
2) Integratsiyalar (check_integrations)
3) Kontent: kontaktlar namunaviy emasmi, yuridik ma'lumotlar, yo'nalishlar, narxlar, ustalar,
   demo ma'lumotlar qolib ketmaganmi, administrator, bildirishnomalar.
Natijada — nimani tuzatish kerakligi ro'yxati.
"""

from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import checks
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

DEFAULT_PHONE = '+998901234567'
DEFAULT_EMAIL = 'info@techservice.uz'


class Command(BaseCommand):
    help = "Ishga tushirishga tayyorlik: xavfsizlik, integratsiyalar va kontent"

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true')
        parser.add_argument('--fail', action='store_true', help="Muammo bo'lsa nol bo'lmagan kod (CI)")

    def handle(self, *args, **options):
        self.problems, self.warnings = [], []
        self.section('1. Xavfsizlik va sozlamalar')
        self.security()
        self.section('2. Integratsiyalar')
        out = StringIO()
        call_command('check_integrations', *(['--live'] if options['live'] else []), stdout=out)
        for line in out.getvalue().splitlines():
            if line.startswith('✗'):
                self.problems.append(line[2:].strip())
            elif line.startswith('!'):
                self.warnings.append(line[2:].strip())
            if line.strip():
                self.stdout.write('   ' + line)
        self.section('3. Kontent va ma\'lumotlar')
        self.content()

        self.stdout.write('')
        if self.problems:
            self.stdout.write(self.style.ERROR(f'Tuzatish shart: {len(self.problems)}'))
            for p in self.problems:
                self.stdout.write(self.style.ERROR(f'  ✗ {p}'))
        if self.warnings:
            self.stdout.write(self.style.WARNING(f"E'tibor bering: {len(self.warnings)}"))
            for w in self.warnings:
                self.stdout.write(self.style.WARNING(f'  ! {w}'))
        if not self.problems and not self.warnings:
            self.stdout.write(self.style.SUCCESS('✓ Hammasi tayyor — saytni ishga tushirish mumkin.'))
        elif not self.problems:
            self.stdout.write(self.style.SUCCESS("✓ Majburiy muammo yo'q; ogohlantirishlarni ko'rib chiqing."))
        if self.problems and options['fail']:
            raise CommandError(f'{len(self.problems)} ta muammo')

    def section(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{title}'))

    def ok(self, text):
        self.stdout.write(self.style.SUCCESS(f'   ✓ {text}'))

    def bad(self, text, hard=True):
        (self.problems if hard else self.warnings).append(text)
        self.stdout.write((self.style.ERROR if hard else self.style.WARNING)(f"   {'✗' if hard else '!'} {text}"))

    def security(self):
        if settings.DEBUG:
            self.bad('DJANGO_DEBUG=True — production\'da False bo\'lishi shart')
        issues = checks.run_checks(include_deployment_checks=True)
        relevant = [i for i in issues if i.level >= checks.WARNING]
        if not relevant:
            self.ok("check --deploy: muammo yo'q")
        for issue in relevant:
            hard = issue.id in ('techservice.W001', 'techservice.W002', 'techservice.W003', 'techservice.W004',
                                'techservice.W006', 'techservice.W008') or issue.id.startswith('security.')
            self.bad(f'{issue.id}: {issue.msg} → {issue.hint or ""}'.strip(' →'), hard=hard and not settings.DEBUG)

    def content(self):
        from masters.models import Category, Master
        from repair_service.models import Service
        info = settings.SITE_INFO
        if info['phone'] == DEFAULT_PHONE or info['email'] == DEFAULT_EMAIL:
            self.bad('Saytdagi telefon yoki email namunaviy — SITE_PHONE, SITE_EMAIL ni kiriting')
        else:
            self.ok(f"Kontaktlar: {info['phone']}, {info['email']}")
        if not (info.get('legal_name') and info.get('legal_inn')):
            self.bad("Yuridik ma'lumotlar yo'q (SITE_LEGAL_NAME, SITE_LEGAL_INN) — oferta va hisob-fakturalarda kerak")
        else:
            self.ok(f"Yuridik shaxs: {info['legal_name']}, STIR {info['legal_inn']}")
        if not get_user_model().objects.filter(is_superuser=True, is_active=True).exists():
            self.bad("Administrator yo'q — python manage.py createsuperuser")
        else:
            self.ok('Administrator bor')
        categories = Category.objects.filter(is_active=True).count()
        services = Service.objects.filter(is_active=True).count()
        (self.ok if categories else self.bad)(f"Faol yo'nalishlar: {categories}")
        if services:
            self.ok(f'Narxlar katalogi: {services} ta xizmat')
        else:
            self.bad("Narxlar katalogi bo'sh — admin → Narxlar", hard=False)
        demo = Master.objects.filter(phone__startswith='+998991000').count()
        if demo:
            self.bad(f"Demo ustalar qolgan ({demo} ta, seed_demo) — haqiqiy saytda mijozlarni chalg'itadi: "
                     "python manage.py seed_demo --reset")
        verified = Master.objects.filter(is_verified=True).exclude(phone__startswith='+998991000').count()
        if verified < 5:
            self.bad(f"Tasdiqlangan ustalar kam ({verified}). Kamida 5–10 ta bilan boshlang — "
                     "/ustalar-uchun/ sahifasi va taklif havolalari", hard=False)
        else:
            self.ok(f'Tasdiqlangan ustalar: {verified}')
        if not getattr(settings, 'TELEGRAM_CHAT_ID', ''):
            self.bad("TELEGRAM_CHAT_ID yo'q — yangi ariza, nizo va yordam savollari haqida xabar olmaysiz", hard=False)
        else:
            self.ok('Administrator Telegram xabarlari yoqilgan')
        if not getattr(settings, 'SENTRY_DSN', ''):
            self.bad("SENTRY_DSN yo'q — saytdagi xatolar faqat logda qoladi (sentry.io yoki o'z Sentry'ingiz)",
                     hard=False)
        else:
            self.ok('Xatolar monitoringi (Sentry) yoqilgan')
        if not settings.WEBPUSH_PRIVATE_KEY:
            self.bad("Brauzer bildirishnomalari o'chiq — python manage.py webpush_keys", hard=False)
