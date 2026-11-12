"""Kelish vaqti, yozishma, ustalarga o'tkazmalar, statistika va yuridik sahifalar."""

from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.core import mail  # noqa: F401
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from openpyxl import load_workbook

from config import stats
from masters.tests import verify_phone
from otp.sms import ConsoleBackend
from payments import payouts
from payments.models import Milestone, Payout
from telegram_bot import client

from . import chat, schedule, workflow
from .models import OrderMessage, ServiceRequest
from .test_warranty import PHONE, confirmed_order
from .tests import AJAX, VALID, make_master


class Base(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        client.SENT.clear()
        self.master = make_master('Usta', '+998911111111')
        self.order = ServiceRequest.objects.create(name='Malika', phone=PHONE, master=self.master)
        workflow.apply(self.order, workflow.MASTER, 'accept')
        self.order.refresh_from_db()
        ConsoleBackend.sent.clear()

    def tearDown(self):
        translation.activate('uz')

    def sms_to(self, phone):
        return [t for p, t in ConsoleBackend.sent if p == phone]


class ScheduleTests(Base):
    def test_arizada_qulay_vaqt(self):
        day = timezone.localdate() + timedelta(days=1)
        data = {**VALID, 'preferred_date': day.isoformat(), 'preferred_slot': 'evening'}
        self.assertEqual(self.client.post(reverse('repair_service:submit_request'), data, **AJAX).status_code, 200)
        order = ServiceRequest.objects.latest('id')
        self.assertEqual((order.preferred_date, order.preferred_slot), (day, 'evening'))
        self.assertIn('16:00–20:00', schedule.preferred_label(order))

        cache.clear()
        past = {**VALID, 'preferred_date': (timezone.localdate() - timedelta(days=1)).isoformat()}
        response = self.client.post(reverse('repair_service:submit_request'), past, **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('preferred_date', response.json()['errors'])

    def test_usta_vaqt_belgilaydi(self):
        self.client.force_login(self.master.user)
        when = timezone.localtime() + timedelta(days=1)
        url = reverse('masters:visit_set', args=[self.order.pk])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {'date': when.strftime('%Y-%m-%d'), 'time': '18:30'})
        self.order.refresh_from_db()
        local = timezone.localtime(self.order.visit_at)
        self.assertEqual((local.date(), local.strftime('%H:%M')), (when.date(), '18:30'))
        self.assertIn('18:30', self.sms_to(PHONE)[-1])
        self.assertTrue(self.order.events.filter(note__contains='Kelish vaqti').exists())
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'id="taqvim"')
        self.assertContains(self.client.get(self.order.get_customer_url()), '18:30')

        # o'tgan vaqt va noto'g'ri format rad etiladi
        before = self.order.visit_at
        self.client.post(url, {'date': '2020-01-01', 'time': '10:00'})
        self.client.post(url, {'date': 'abc', 'time': ''})
        self.order.refresh_from_db()
        self.assertEqual(self.order.visit_at, before)

    def test_joyga_kelgach_ozgartirib_bolmaydi_va_begona_usta(self):
        other = make_master('Begona', '+998922222222')
        self.client.force_login(other.user)
        url = reverse('masters:visit_set', args=[self.order.pk])
        self.assertEqual(self.client.post(url, {'date': '2030-01-01', 'time': '10:00'}).status_code, 404)
        workflow.apply(self.order, workflow.MASTER, 'arrive')
        with self.assertRaises(schedule.ScheduleError):
            schedule.set_visit(self.order, timezone.now() + timedelta(hours=3))

    def test_toqnashuv_va_taqvim(self):
        when = timezone.now() + timedelta(hours=5)
        schedule.set_visit(self.order, when)
        second = ServiceRequest.objects.create(name='Ali', phone='+998903334455', master=self.master)
        workflow.apply(second, workflow.MASTER, 'accept')
        self.assertEqual(schedule.conflicts(second, when + timedelta(minutes=30)), [self.order])
        self.assertEqual(schedule.conflicts(second, when + timedelta(hours=2)), [])
        calendar = schedule.calendar(self.master)
        self.assertEqual([o.pk for d in calendar['days'] for o in d['orders']], [self.order.pk])
        self.assertEqual(calendar['unscheduled'], [second])

    def test_eslatma_bir_marta(self):
        schedule.set_visit(self.order, timezone.now() + timedelta(hours=1))
        ConsoleBackend.sent.clear()
        call_command('process_orders', verbosity=0)
        self.assertIn('Eslatma', self.sms_to(PHONE)[-1])
        self.assertIn('Eslatma', self.sms_to(self.master.phone)[-1])
        count = len(ConsoleBackend.sent)
        call_command('process_orders', verbosity=0)
        self.assertEqual(len(ConsoleBackend.sent), count)
        # uzoqdagi tashrifga eslatma bormaydi
        far = ServiceRequest.objects.create(name='Ali', phone='+998903334455', master=self.master)
        workflow.apply(far, workflow.MASTER, 'accept')
        schedule.set_visit(far, timezone.now() + timedelta(hours=9))
        self.assertEqual(schedule.send_reminders(), [])


class ChatTests(Base):
    def setUp(self):
        super().setUp()
        self.c_url = reverse('repair_service:order_chat', args=[self.order.review_token])
        self.m_url = reverse('masters:order_chat', args=[self.order.pk])

    def test_mijoz_tasdiqlanmagan_bolsa_yopiq(self):
        chat.send(self.order, chat.MASTER, 'Maxfiy xabar')
        self.assertEqual(self.client.get(self.c_url).status_code, 404)
        self.assertEqual(self.client.post(self.c_url, {'text': 'Salom'}).status_code, 404)
        self.assertNotContains(self.client.get(self.order.get_customer_url()), 'Maxfiy xabar')

    def test_yozishma_va_oqilgan_belgisi(self):
        verify_phone(self.client, PHONE)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.c_url, {'text': ' Qachon kelasiz? '}, **AJAX)
        data = response.json()
        self.assertEqual([(m['text'], m['mine']) for m in data['messages']], [('Qachon kelasiz?', True)])
        self.assertIn('xabar yozdi', self.sms_to(self.master.phone)[-1])
        self.assertEqual(chat.unread_count(self.order, chat.MASTER), 1)

        usta = self.client_class()
        usta.force_login(self.master.user)
        self.assertContains(usta.get(reverse('masters:dashboard')), 'badge--unread')
        self.assertContains(usta.get(self.order.get_master_url()), 'Qachon kelasiz?')
        self.assertEqual(chat.unread_count(self.order, chat.MASTER), 0)
        usta.post(self.m_url, {'text': '18:00 da'}, **AJAX)
        last = data['messages'][-1]['id']
        fresh = self.client.get(self.c_url, {'after': last}, **AJAX).json()
        self.assertEqual([(m['text'], m['mine']) for m in fresh['messages']], [('18:00 da', False)])

    def test_html_qochiriladi(self):
        chat.send(self.order, chat.CUSTOMER, '<script>alert(1)</script>')
        self.client.force_login(self.master.user)
        response = self.client.get(self.order.get_master_url())
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_sms_cheklangan_telegram_har_safar(self):
        with self.captureOnCommitCallbacks(execute=True):
            chat.send(self.order, chat.MASTER, 'Bir')
            chat.send(self.order, chat.MASTER, 'Ikki')
        self.assertEqual(len(self.sms_to(PHONE)), 1)        # SMS pullik — suhbatga bitta
        self.assertNotIn('Bir', self.sms_to(PHONE)[0])      # SMS'da xabar matni yo'q
        self.order.telegram_chat_id = 555
        self.order.save()
        with self.captureOnCommitCallbacks(execute=True):
            chat.send(self.order, chat.MASTER, 'Uch')
            chat.send(self.order, chat.MASTER, "To'rt")
        texts = [p['text'] for m, p in client.SENT if p.get('chat_id') == 555]
        self.assertEqual(len(texts), 2)
        self.assertIn('Uch', texts[0])

    def test_cheklovlar(self):
        for bad in ('', '   ', 'x' * 1001):
            with self.assertRaises(chat.ChatError):
                chat.send(self.order, chat.CUSTOMER, bad)
        fresh = ServiceRequest.objects.create(name='A', phone=PHONE)          # ustasi yo'q
        self.assertFalse(chat.can_send(fresh))
        workflow.apply(self.order, workflow.CUSTOMER, 'cancel')
        self.order.refresh_from_db()
        with self.assertRaises(chat.ChatError):
            chat.send(self.order, chat.MASTER, 'Salom')

    def test_tezlik_chegarasi(self):
        for i in range(chat.PER_MINUTE):
            chat.send(self.order, chat.CUSTOMER, f'xabar {i}')
        with self.assertRaises(chat.ChatError):
            chat.send(self.order, chat.CUSTOMER, 'yana')

    @override_settings(CHAT_OPEN_DAYS=30)
    def test_tasdiqlangach_muddat(self):
        recent = confirmed_order(self.master)
        self.assertTrue(chat.can_send(recent))
        old = confirmed_order(self.master, days_ago=31)
        self.assertFalse(chat.can_send(old))

    def test_begona_usta_va_oddiy_post(self):
        other = make_master('Begona', '+998922222222')
        self.client.force_login(other.user)
        self.assertEqual(self.client.get(self.m_url).status_code, 404)
        self.client.force_login(self.master.user)
        response = self.client.post(self.m_url, {'text': 'JS siz'})
        self.assertRedirects(response, self.order.get_master_url() + '#chat', fetch_redirect_response=False)
        self.assertTrue(OrderMessage.objects.filter(text='JS siz', sender='master').exists())


class PayoutTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        self.master = make_master('Usta', '+998911111111')
        self.master.payout_card, self.master.payout_holder = '8600123412341234', 'USTA USTAYEV'
        self.master.save()
        self.nocard = make_master('Kartasiz', '+998922222222')
        confirmed_order(self.master, plan='on_completion')
        confirmed_order(self.master, plan='on_completion')
        confirmed_order(self.nocard, plan='on_completion')
        confirmed_order(self.master, plan='cash')               # naqd — hisobotga kirmaydi
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'x')
        self.client.force_login(self.admin)
        self.url = reverse('admin:payments_payout_pending')

    def test_kutayotganlar(self):
        rows = {r['master'].pk: r for r in payouts.pending()}
        row = rows[self.master.pk]
        self.assertEqual((row['count'], row['gross'], row['fee'], row['amount']), (2, 600000, 60000, 540000))
        self.assertFalse(rows[self.nocard.pk]['has_card'])
        response = self.client.get(self.url)
        self.assertContains(response, '8600 1234 1234 1234')
        self.assertContains(response, 'Karta kiritilmagan')

    def test_excel(self):
        response = self.client.get(self.url, {'format': 'xlsx'})
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        rows = list(sheet.iter_rows(values_only=True))
        usta = next(r for r in rows[1:] if r[0] == 'Usta')
        self.assertEqual((usta[2], usta[7]), ('8600 1234 1234 1234', 540000))
        self.assertEqual((rows[-1][0], rows[-1][7]), ('JAMI', 810000))

    def test_excel_formula_inyeksiyasi(self):
        self.master.payout_holder = '=HYPERLINK("http://evil")'
        self.master.save()
        sheet = load_workbook(BytesIO(payouts.pending_xlsx())).active
        cell = next(r for r in sheet.iter_rows(min_row=2) if r[0].value == 'Usta')[3]
        self.assertTrue(cell.value.startswith("'="))
        self.assertNotEqual(cell.data_type, 'f')

    def test_otkazildi_deb_belgilash(self):
        self.client.post(self.url, {'master': [self.master.pk, self.nocard.pk], 'note': 'TT-15'})
        payout = Payout.objects.get()                            # kartasiz ustaga yaratilmaydi
        self.assertEqual((payout.master, payout.amount, payout.count, payout.card, payout.note, payout.created_by),
                         (self.master, 540000, 2, '8600123412341234', 'TT-15', self.admin))
        self.assertEqual(payout.milestones.count(), 2)
        self.assertFalse(Milestone.objects.filter(order__master=self.master, paid_out_at__isnull=True,
                                                  state='released').exists())
        self.assertEqual([r['master'] for r in payouts.pending()], [self.nocard])
        self.client.post(self.url, {'master': [self.master.pk]})  # takror — yangi yozuv yo'q
        self.assertEqual(Payout.objects.count(), 1)

        self.assertEqual(self.client.get(reverse('admin:payments_payout_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:payments_payout_change', args=[payout.pk])).status_code, 200)
        response = self.client.post(reverse('admin:payments_payout_changelist'), {
            'action': 'export_xlsx', '_selected_action': [payout.pk]})
        self.assertEqual(load_workbook(BytesIO(response.content)).active['I2'].value, 540000)

    def test_admin_emas(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.master.user)
        self.assertEqual(self.client.get(self.url, {'format': 'xlsx'}).status_code, 302)

    def test_usta_kartani_kiritadi(self):
        self.client.force_login(self.nocard.user)
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'Karta kiritilmagan')
        form = self.client.get(reverse('masters:profile_edit')).context['form']
        data = {k: v for k, v in form.initial.items() if v is not None and k != 'photo'}
        from masters.models import Category
        data['categories'] = [Category.objects.create(name='Santexnik', slug='santexnik').pk]
        self.client.post(reverse('masters:profile_edit'), {**data, 'payout_card': '9860 1234'})
        self.nocard.refresh_from_db()
        self.assertEqual(self.nocard.payout_card, '')
        response = self.client.post(reverse('masters:profile_edit'), {
            **data, 'payout_card': '9860 1234 5678 9012', 'payout_holder': 'K K'})
        self.assertEqual(response.status_code, 302, response.context and response.context['form'].errors)
        self.nocard.refresh_from_db()
        self.assertEqual(self.nocard.payout_card, '9860123456789012')
        self.assertNotContains(self.client.get(self.nocard.get_absolute_url()), '9860')   # ommaviy sahifada yo'q


class StatsAndLegalTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')

    def tearDown(self):
        translation.activate('uz')

    def test_statistika(self):
        master = make_master('Usta', '+998911111111')
        confirmed_order(master, plan='on_completion')
        confirmed_order(master, plan='cash')
        ServiceRequest.objects.create(name='Yangi', phone=PHONE)
        old = ServiceRequest.objects.create(name='Eski', phone=PHONE)
        ServiceRequest.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=60))
        data = stats.collect(30)
        self.assertEqual([f['count'] for f in data['funnel']], [3, 2, 2, 2])
        kpi = {k['title']: k['value'] for k in data['kpis']}
        self.assertEqual(kpi['Arizalar'], 3)
        self.assertEqual(kpi["O'rtacha chek"], '300 000')
        self.assertEqual(kpi['Aylanma (GMV)'], '600 000')
        self.assertEqual(kpi['Platforma daromadi'], '30 000')
        self.assertEqual(data['top_masters'][0]['done'], 2)
        self.assertEqual(stats.collect(90)['total'], 4)

        url = reverse('admin_stats')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(master.user)
        self.assertEqual(self.client.get(url).status_code, 302)          # usta — admin emas
        self.client.force_login(User.objects.create_superuser('admin', 'a@example.com', 'x'))
        for query in ('', '?days=7', '?days=365', '?days=abc', '?days=13'):
            self.assertContains(self.client.get(url + query), 'Voronka')

    def test_bosh_statistika(self):
        self.assertEqual(stats.collect(7)['total'], 0)

    @override_settings(LEGAL_DRAFT=True, PLATFORM_FEE_PERCENT=10.0, WARRANTY_DAYS=30)
    def test_yuridik_sahifalar(self):
        response = self.client.get(reverse('repair_service:offer'))
        self.assertContains(response, 'Ommaviy oferta')
        self.assertContains(response, '10% komissiya')
        self.assertContains(response, '30 kun kafolat')
        self.assertContains(response, 'Loyiha.')
        self.assertContains(self.client.get(reverse('repair_service:privacy')), "O'RQ-547")
        self.assertContains(self.client.get('/ru/oferta/'), 'публичная оферта')
        self.assertContains(self.client.get('/ru/maxfiylik/'), 'ЗРУ-547')
        self.assertContains(self.client.get('/'), reverse('repair_service:privacy'))
        with override_settings(LEGAL_DRAFT=False):
            self.assertNotContains(self.client.get(reverse('repair_service:offer')), 'Loyiha.')
