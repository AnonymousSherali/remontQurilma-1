"""Tashqi xizmatlar sozlamalarini tekshirish.

    python manage.py check_integrations          # sozlamalar + saytning o'z endpointlari (tarmoqsiz)
    python manage.py check_integrations --live   # + Eskiz, Telegram va SITE_URL ga haqiqiy so'rov

Nima tekshiriladi:
- sozlama: kerakli kalitlar to'ldirilganmi, formati to'g'rimi;
- endpoint (o'z-o'zini sinash): Payme / Click / Uzum so'rovi .env dagi kalit bilan
  imzolanib saytning O'Z endpointiga yuboriladi — kalit noto'g'ri yozilgan bo'lsa,
  to'lov tizimi ham rad javobini oladi. Hech narsa yaratilmaydi va o'zgarmaydi
  (mavjud bo'lmagan hisob raqami so'raladi);
- --live: Eskiz'ga kirish (SMS yuborilmaydi), Telegram getMe / getWebhookInfo, SITE_URL/healthz/.

To'lov tizimining O'Z tomonini (sizning kabinetingiz, sandbox) bu buyruq tekshira olmaydi —
buning uchun docs/INTEGRATSIYALAR.md dagi qadamlar.
"""

import base64
import json
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

OK, FAIL, SKIP, WARN = 'ok', 'fail', 'skip', 'warn'
MARKS = {OK: '✓', FAIL: '✗', SKIP: '–', WARN: '!'}
MISSING_ACCOUNT = '999999999'   # mavjud bo'lmagan hisob — hech narsa o'zgarmaydi


def _providers():
    return [p.strip() for p in settings.PAYMENT_PROVIDERS.split(',') if p.strip()]


def _missing(*names):
    return [n for n in names if not getattr(settings, n, '')]


class Command(BaseCommand):
    help = "To'lov tizimlari, SMS va Telegram sozlamalarini tekshiradi"

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true', help="Eskiz, Telegram va SITE_URL ga haqiqiy so'rov")
        parser.add_argument('--fail', action='store_true', help="Xato bo'lsa nol bo'lmagan kod bilan chiqish (CI)")

    def handle(self, *args, **options):
        self.results = []
        self.client = Client(HTTP_HOST=(settings.ALLOWED_HOSTS or ['localhost'])[0].lstrip('.').replace('*', 'localhost'))
        self.live = options['live']
        self.site()
        self.sms(options['live'])
        self.payme()
        self.click()
        self.uzum()
        self.telegram(options['live'])
        self.webpush()
        failed = [r for r in self.results if r[1] == FAIL]
        self.stdout.write('')
        summary = f"{sum(r[1] == OK for r in self.results)} ✓, {len(failed)} ✗, " \
                  f"{sum(r[1] == WARN for r in self.results)} !, {sum(r[1] == SKIP for r in self.results)} –"
        self.stdout.write(self.style.ERROR(summary) if failed else self.style.SUCCESS(summary))
        if failed and options['fail']:
            raise CommandError(f'{len(failed)} ta tekshiruv muvaffaqiyatsiz')

    # ---------- chiqarish ----------

    def report(self, name, status, text, hint=''):
        self.results.append((name, status, text))
        style = {OK: self.style.SUCCESS, FAIL: self.style.ERROR, WARN: self.style.WARNING}.get(status, str)
        self.stdout.write(style(f'{MARKS[status]} {name:<10} {text}'))
        if hint:
            self.stdout.write(f'             → {hint}')

    def post(self, url, **kwargs):
        return self.client.post(url, secure=True, **kwargs)

    # ---------- sayt ----------

    def site(self):
        url = settings.SITE_URL
        if url.startswith('https://'):
            self.report('Sayt', OK, url)
        else:
            self.report('Sayt', WARN, f"{url} — HTTPS emas", "Payme, Click va Telegram faqat HTTPS manzilga murojaat qiladi")
        if self.live:
            try:
                with urllib.request.urlopen(url.rstrip('/') + '/healthz/', timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                self.report('Sayt', OK if data.get('status') == 'ok' else FAIL, f'healthz: {data}')
            except Exception as error:  # noqa: BLE001
                self.report('Sayt', FAIL, f'{url}/healthz/ ochilmadi: {error}',
                            "Sayt internetdan ochilishi kerak — aks holda to'lov tizimlari unga ulana olmaydi")

    # ---------- SMS ----------

    def sms(self, live):
        if settings.SMS_BACKEND != 'eskiz':
            self.report('SMS', WARN, f'SMS_BACKEND={settings.SMS_BACKEND} — kodlar faqat logga yoziladi',
                        'SMS_BACKEND=eskiz')
            return
        missing = _missing('ESKIZ_EMAIL', 'ESKIZ_PASSWORD', 'SMS_SENDER')
        if missing:
            self.report('SMS', FAIL, "to'ldirilmagan: " + ', '.join(missing))
            return
        self.report('SMS', OK, f'Eskiz, jo\'natuvchi {settings.SMS_SENDER}')
        if not live:
            return
        from otp.sms import EskizBackend
        try:
            EskizBackend()._token(refresh=True)
            self.report('SMS', OK, "Eskiz: kirish muvaffaqiyatli (SMS yuborilmadi)",
                        "Matnlar shablon sifatida Eskiz kabinetida tasdiqlanganini ham tekshiring")
        except Exception as error:  # noqa: BLE001
            self.report('SMS', FAIL, f'Eskiz: kirib bo\'lmadi — {error}', 'ESKIZ_EMAIL / ESKIZ_PASSWORD ni tekshiring')

    # ---------- Payme ----------

    def payme(self):
        if 'payme' not in _providers():
            self.report('Payme', SKIP, "PAYMENT_PROVIDERS da yo'q")
            return
        missing = _missing('PAYME_MERCHANT_ID', 'PAYME_KEY')
        if missing:
            self.report('Payme', FAIL, "to'ldirilmagan: " + ', '.join(missing))
            return
        mode = 'SINOV (test.paycom.uz)' if settings.PAYME_TEST else 'HAQIQIY (checkout.paycom.uz)'
        self.report('Payme', WARN if settings.PAYME_TEST else OK, f'kassa {settings.PAYME_MERCHANT_ID}, rejim: {mode}',
                    'Sinovdan keyin PAYME_TEST=False va haqiqiy kalit' if settings.PAYME_TEST else '')
        url = reverse('payme_endpoint')
        body = json.dumps({'id': 1, 'method': 'CheckPerformTransaction',
                           'params': {'amount': 100000, 'account': {settings.PAYME_ACCOUNT_KEY: MISSING_ACCOUNT}}})
        auth = 'Basic ' + base64.b64encode(f'Paycom:{settings.PAYME_KEY}'.encode()).decode()
        data = self.post(url, data=body, content_type='application/json', HTTP_AUTHORIZATION=auth).json()
        code = (data.get('error') or {}).get('code')
        if code == -31050:
            self.report('Payme', OK, f'endpoint {settings.SITE_URL.rstrip("/")}{url} kalitni qabul qildi')
        else:
            self.report('Payme', FAIL, f'endpoint kutilmagan javob berdi: {data}')

    # ---------- Click ----------

    def click(self):
        if 'click' not in _providers():
            self.report('Click', SKIP, "PAYMENT_PROVIDERS da yo'q")
            return
        missing = _missing('CLICK_SERVICE_ID', 'CLICK_MERCHANT_ID', 'CLICK_SECRET_KEY', 'CLICK_MERCHANT_USER_ID')
        if missing:
            self.report('Click', FAIL, "to'ldirilmagan: " + ', '.join(missing))
            return
        from payments.click import make_sign
        data = {'click_trans_id': '1', 'service_id': settings.CLICK_SERVICE_ID, 'click_paydoc_id': '1',
                'merchant_trans_id': MISSING_ACCOUNT, 'amount': '1000', 'action': '0', 'error': '0',
                'error_note': 'Success', 'sign_time': time.strftime('%Y-%m-%d %H:%M:%S')}
        data['sign_string'] = make_sign(data)
        reply = self.post(reverse('click_prepare'), data=data).json()
        base = settings.SITE_URL.rstrip('/')
        if reply.get('error') == -5:
            self.report('Click', OK, f'Prepare/Complete: {base}{reverse("click_prepare")}, {base}{reverse("click_complete")}')
        else:
            self.report('Click', FAIL, f'endpoint kutilmagan javob berdi: {reply}')

    # ---------- Uzum ----------

    def uzum(self):
        if 'uzum' not in _providers():
            self.report('Uzum', SKIP, "PAYMENT_PROVIDERS da yo'q")
            return
        missing = _missing('UZUM_SERVICE_ID', 'UZUM_LOGIN', 'UZUM_PASSWORD')
        if missing:
            self.report('Uzum', FAIL, "to'ldirilmagan: " + ', '.join(missing))
            return
        auth = 'Basic ' + base64.b64encode(f'{settings.UZUM_LOGIN}:{settings.UZUM_PASSWORD}'.encode()).decode()
        body = json.dumps({'serviceId': int(settings.UZUM_SERVICE_ID) if settings.UZUM_SERVICE_ID.isdigit()
                           else settings.UZUM_SERVICE_ID, 'timestamp': int(time.time() * 1000),
                           'params': {settings.UZUM_ACCOUNT_KEY: MISSING_ACCOUNT}})
        response = self.post(reverse('uzum_endpoint', args=['check']), data=body, content_type='application/json',
                             HTTP_AUTHORIZATION=auth)
        data = response.json()
        if data.get('errorCode') == '10007':
            self.report('Uzum', WARN, 'endpoint kalitni qabul qildi',
                        "Protokol Uzum rasmiy hujjati bilan solishtirilmagan — README'ga qarang")
        else:
            self.report('Uzum', FAIL, f'endpoint kutilmagan javob berdi: {data}')

    # ---------- Web Push ----------

    def webpush(self):
        from repair_service import webpush
        from repair_service.models import PushSubscription
        if not webpush.enabled():
            self.report('Push', SKIP, "WEBPUSH_* kalitlari yo'q — brauzer bildirishnomalari o'chiq",
                        'python manage.py webpush_keys')
            return
        try:
            webpush.vapid_headers('https://fcm.googleapis.com/fcm/send/x')
        except Exception as error:  # noqa: BLE001
            self.report('Push', FAIL, f"WEBPUSH_PRIVATE_KEY noto'g'ri: {error}", 'python manage.py webpush_keys')
            return
        self.report('Push', OK, f'kalitlar to\'g\'ri, obunalar: {PushSubscription.objects.count()}')

    # ---------- Telegram ----------

    def telegram(self, live):
        missing = _missing('TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME', 'TELEGRAM_WEBHOOK_SECRET')
        if len(missing) == 3:
            self.report('Telegram', SKIP, 'sozlanmagan — xabarlar SMS orqali')
            return
        if missing:
            self.report('Telegram', FAIL, "to'ldirilmagan: " + ', '.join(missing))
            return
        self.report('Telegram', OK, f'@{settings.TELEGRAM_BOT_USERNAME}')
        if not live:
            return
        from telegram_bot import client
        try:
            me = client.api('getMe', {}).get('result') or {}
            info = client.api('getWebhookInfo', {}).get('result') or {}
        except urllib.error.HTTPError as error:
            self.report('Telegram', FAIL, f'API xatosi {error.code}', 'TELEGRAM_BOT_TOKEN ni tekshiring')
            return
        except Exception as error:  # noqa: BLE001
            self.report('Telegram', FAIL, f'API ga ulanib bo\'lmadi: {error}')
            return
        if me.get('username', '').lower() != settings.TELEGRAM_BOT_USERNAME.lower():
            self.report('Telegram', FAIL, f"token @{me.get('username')} botiga tegishli, "
                                          f"TELEGRAM_BOT_USERNAME={settings.TELEGRAM_BOT_USERNAME}")
        expected = settings.SITE_URL.rstrip('/') + reverse('telegram_webhook')
        if info.get('url') != expected:
            self.report('Telegram', FAIL, f"webhook: {info.get('url') or 'ulanmagan'}",
                        f'python manage.py telegram_webhook  (kutilgan: {expected})')
        elif info.get('last_error_message'):
            self.report('Telegram', WARN, f"webhook xatosi: {info['last_error_message']}",
                        f"navbatda {info.get('pending_update_count', 0)} ta xabar")
        else:
            self.report('Telegram', OK, f'webhook ulangan: {expected}')

