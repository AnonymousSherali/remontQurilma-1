import base64
import json
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from masters.models import Master
from masters.tests import verify_phone
from otp.sms import ConsoleBackend
from repair_service import workflow
from repair_service.models import ServiceRequest
from repair_service.tests import AJAX, VALID, make_master

from . import promos, services
from .models import PromoCode, PromoRedemption

PHONE = '+998901112233'
FRIEND = '+998907778899'


def order_with_quote(master, phone=PHONE, amount=300000, plan='thirds', code=None):
    order = ServiceRequest.objects.create(name='Malika', phone=phone, master=master)
    if code:
        promos.apply(order, code)
    workflow.apply(order, workflow.MASTER, 'accept')
    services.propose_quote(order, amount, plan)
    services.approve_quote(order)
    return order


def finish(order):
    for m in order.milestones.all():
        services.mark_held(m)
    for action in ('arrive', 'start', 'complete'):
        workflow.apply(order, workflow.MASTER, action)
    workflow.apply(order, workflow.CUSTOMER, 'confirm')
    order.refresh_from_db()
    return order


class PromoTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        self.master = make_master('Usta', '+998911111111')
        self.promo = PromoCode.objects.create(code='yangi10', kind='percent', value=10, max_discount=25000)

    def test_chegirma_taqsimlanadi_usta_toliq_oladi(self):
        order = order_with_quote(self.master, code='YANGI10')
        ms = list(order.milestones.order_by('position'))
        self.assertEqual(sum(m.discount for m in ms), 25000)                  # 10% = 30 000, chegara 25 000
        self.assertEqual([m.discount for m in ms], [8333, 8333, 8334])
        self.assertEqual([m.amount_due for m in ms], [91667, 91667, 91666])
        self.assertEqual(ms[0].master_amount, ms[0].amount - ms[0].fee_amount)  # usta chegirmadan bexabar
        self.assertEqual(PromoRedemption.objects.get().discount, 25000)

    def test_naqd_rejada_chegirma_yoq(self):
        order = order_with_quote(self.master, code='YANGI10', plan='cash')
        self.assertEqual(PromoRedemption.objects.get(order=order).discount, 0)

    def test_eng_kop_ulush_va_qatiy_summa(self):
        PromoCode.objects.create(code='KATTA', kind='fixed', value=900000)
        order = order_with_quote(self.master, amount=100000, plan='on_completion', code='KATTA')
        self.assertEqual(order.milestones.get().discount, 50000)              # PROMO_MAX_SHARE_PERCENT=50

    def test_tekshiruvlar(self):
        with self.assertRaises(promos.PromoError):
            promos.validate('yoq', PHONE)
        PromoCode.objects.create(code='ESKI', kind='percent', value=5, valid_until=timezone.now() - timedelta(days=1))
        with self.assertRaises(promos.PromoError):
            promos.validate('eski', PHONE)
        order_with_quote(self.master, code='YANGI10')
        with self.assertRaises(promos.PromoError):                           # bitta raqamga bir marta
            promos.validate('YANGI10', PHONE)
        self.promo.max_uses = 1
        self.promo.save()
        with self.assertRaises(promos.PromoError):                           # umumiy limit
            promos.validate('YANGI10', FRIEND)

    def test_tolovdan_keyin_qoshib_bolmaydi(self):
        order = order_with_quote(self.master)
        services.mark_held(order.milestones.first())
        with self.assertRaises(promos.PromoError):
            promos.apply(order, 'YANGI10')

    @override_settings(PAYME_KEY='secret', PAYME_ACCOUNT_KEY='milestone_id', PAYMENT_PROVIDERS='payme')
    def test_payme_chegirmali_summani_talab_qiladi(self):
        order = order_with_quote(self.master, plan='on_completion', code='YANGI10')
        m = order.milestones.get()
        auth = 'Basic ' + base64.b64encode(b'Paycom:secret').decode()

        def rpc(amount):
            return self.client.post(reverse('payme_endpoint'), json.dumps({
                'method': 'CheckPerformTransaction', 'id': 1,
                'params': {'amount': amount, 'account': {'milestone_id': m.pk}}}),
                content_type='application/json', HTTP_AUTHORIZATION=auth).json()
        self.assertEqual(rpc(300000 * 100)['error']['code'], -31001)          # chegirmasiz summa — rad
        self.assertTrue(rpc(275000 * 100)['result']['allow'])

    def test_ariza_formasida_kod(self):
        response = self.client.post(reverse('repair_service:submit_request'), {**VALID, 'promo_code': 'yoq'}, **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('promo_code', response.json()['errors'])
        cache.clear()
        self.client.post(reverse('repair_service:submit_request'), {**VALID, 'promo_code': 'yangi10'}, **AJAX)
        order = ServiceRequest.objects.latest('id')
        self.assertEqual(order.promo_redemption.promo, self.promo)
        self.assertContains(self.client.get('/?promo=YANGI10'), 'value="YANGI10"')

    def test_buyurtma_sahifasida_qollash_va_olib_tashlash(self):
        order = order_with_quote(self.master)
        url = reverse('repair_service:promo_apply', args=[order.review_token])
        self.assertEqual(self.client.post(url, {'code': 'YANGI10'}).status_code, 404)     # SMS kodsiz
        verify_phone(self.client, PHONE)
        self.client.post(url, {'code': 'yangi10'})
        self.assertEqual(promos.total_discount(order), 25000)
        page = self.client.get(order.get_customer_url())
        self.assertContains(page, 'YANGI10')
        self.assertContains(page, '<s class="muted small"', count=3)
        self.client.post(url, {'remove': '1'})
        self.assertEqual(promos.total_discount(order), 0)
        self.assertFalse(PromoRedemption.objects.exists())


class ReferralTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        ConsoleBackend.sent.clear()
        self.master = make_master('Usta', '+998911111111')

    def test_mijoz_referali(self):
        first = finish(order_with_quote(self.master))
        self.assertTrue(promos.can_refer(PHONE))
        verify_phone(self.client, PHONE)
        page = self.client.get(first.get_customer_url())
        code = PromoCode.objects.get(purpose='referral', owner_phone=PHONE)
        self.assertContains(page, f'?promo={code.code}')
        with self.assertRaises(promos.PromoError):                           # o'z kodini ishlata olmaydi
            promos.validate(code.code, PHONE)

        with self.captureOnCommitCallbacks(execute=True):
            friend_order = finish(order_with_quote(self.master, phone=FRIEND, code=code.code))
        self.assertEqual(promos.total_discount(friend_order), 30000)        # 10% (chegara 50 000)
        reward = PromoCode.objects.get(purpose='reward')
        self.assertEqual((reward.only_phone, reward.max_uses), (PHONE, 1))
        self.assertIn(reward.code, [t for p, t in ConsoleBackend.sent if p == PHONE][-1])
        with self.assertRaises(promos.PromoError):                           # mukofot faqat egasiga
            promos.validate(reward.code, FRIEND)
        with self.assertRaises(promos.PromoError):                           # do'st kodi faqat birinchi buyurtmaga
            promos.validate(code.code, FRIEND)
        promos.on_confirmed(friend_order)
        self.assertEqual(PromoCode.objects.filter(purpose='reward').count(), 1)   # ikki marta berilmaydi

    def test_naqd_buyurtmada_mukofot_yoq(self):
        finish(order_with_quote(self.master))
        code = promos.referral_code_for(PHONE)
        with self.captureOnCommitCallbacks(execute=True):
            finish(order_with_quote(self.master, phone=FRIEND, code=code.code, plan='cash'))
        self.assertFalse(PromoCode.objects.filter(purpose='reward').exists())

    def test_usta_referali(self):
        self.client.force_login(self.master.user)
        page = self.client.get(reverse('masters:dashboard'))
        self.master.refresh_from_db()
        link = f'?ref={self.master.referral_code}'
        self.assertContains(page, link)
        self.client.logout()

        self.client.get(reverse('masters:register') + link)
        session = self.client.session
        self.assertEqual(session['master_ref'], self.master.referral_code)
        # Ro'yxatdan o'tish formasini to'ldirish o'rniga — xuddi shu natija (formaning o'zi alohida testlangan)
        newbie = make_master('Yangi', '+998944444444', referred_by=self.master)
        with self.captureOnCommitCallbacks(execute=True):
            finish(order_with_quote(newbie, phone=FRIEND))
        self.master.refresh_from_db()
        newbie.refresh_from_db()
        self.assertTrue(newbie.referral_rewarded)
        self.assertTrue(self.master.is_promoted)
        self.assertIn('bepul TOP', [t for p, t in ConsoleBackend.sent if p == self.master.phone][-1])
        promo_until = self.master.promoted_until
        with self.captureOnCommitCallbacks(execute=True):
            finish(order_with_quote(newbie, phone=PHONE))
        self.master.refresh_from_db()
        self.assertEqual(self.master.promoted_until, promo_until)          # bir marta

    def test_royxatdan_otishda_boglanadi(self):
        self.master.referral_code = 'UABCDE'
        self.master.save()
        from masters.models import Category
        cat = Category.objects.create(name='Santexnik', slug='santexnik')
        self.client.get(reverse('masters:register') + '?ref=uabcde')
        verify_phone(self.client, '+998955555555', purpose='register')
        self.client.post(reverse('masters:register'), {
            'full_name': 'Yangi Usta', 'phone': '+998 (95) 555-55-55', 'password1': 'Kuchli-parol-77',
            'password2': 'Kuchli-parol-77', 'categories': [cat.pk], 'experience_years': 2, 'service_radius_km': 10,
            'latitude': '41.3111', 'longitude': '69.2799', 'consent': 'on'})
        newbie = Master.objects.get(phone='+998955555555')
        self.assertEqual(newbie.referred_by, self.master)


class PromoAdminTests(TestCase):
    def test_admin(self):
        from django.contrib.auth.models import User
        PromoCode.objects.create(code='AKSIYA', kind='fixed', value=20000)
        self.client.force_login(User.objects.create_superuser('a', 'a@example.com', 'x'))
        self.assertContains(self.client.get(reverse('admin:payments_promocode_changelist')), 'AKSIYA')
        self.client.post(reverse('admin:payments_promocode_add'), {
            'code': 'yoz2027', 'purpose': 'promo', 'is_active': 'on', 'kind': 'percent', 'value': '15',
            'min_amount': '0', 'per_phone_limit': '1', 'redemptions-TOTAL_FORMS': 0, 'redemptions-INITIAL_FORMS': 0})
        self.assertTrue(PromoCode.objects.filter(code='YOZ2027').exists())   # katta harfga o'tadi
        self.assertEqual(Decimal(PromoCode.objects.get(code='YOZ2027').value), 15)
