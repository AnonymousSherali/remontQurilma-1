from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import PhoneCode
from .sms import ConsoleBackend

PHONE = '+998901234567'


class OtpServiceTests(TestCase):
    def setUp(self):
        ConsoleBackend.sent.clear()

    def test_kod_yuboriladi_va_xesh_saqlanadi(self):
        code = services.send_code(PHONE, 'login')
        self.assertEqual(len(code), 6)
        self.assertIn(code, ConsoleBackend.sent[-1][1])
        record = PhoneCode.objects.get()
        self.assertNotEqual(record.code_hash, code)  # kodning o'zi saqlanmaydi

    def test_togri_kod(self):
        code = services.send_code(PHONE, 'login')
        self.assertTrue(services.verify_code(PHONE, code, 'login'))
        with self.assertRaises(services.OtpError):  # bir martalik
            services.verify_code(PHONE, code, 'login')

    def test_boshqa_maqsad_uchun_ishlamaydi(self):
        code = services.send_code(PHONE, 'login')
        with self.assertRaises(services.OtpError):
            services.verify_code(PHONE, code, 'register')

    def test_urinishlar_cheklangan(self):
        code = services.send_code(PHONE, 'login')
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(services.MAX_ATTEMPTS):
            with self.assertRaises(services.OtpError):
                services.verify_code(PHONE, wrong, 'login')
        with self.assertRaises(services.OtpError):  # to'g'ri kod ham endi ishlamaydi
            services.verify_code(PHONE, code, 'login')

    def test_muddati_otgan(self):
        code = services.send_code(PHONE, 'login')
        PhoneCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(services.OtpError):
            services.verify_code(PHONE, code, 'login')

    def test_qayta_yuborish_cheklovi(self):
        services.send_code(PHONE, 'login')
        with self.assertRaises(services.OtpError):  # 60 soniya o'tmagan
            services.send_code(PHONE, 'login')
        PhoneCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        services.send_code(PHONE, 'login')
        for _ in range(3):
            PhoneCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
            services.send_code(PHONE, 'login')
        PhoneCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        with self.assertRaises(services.OtpError):  # soatiga 5 tadan ko'p emas
            services.send_code(PHONE, 'login')


class OtpViewTests(TestCase):
    def test_yuborish_va_tasdiqlash_sessiyaga_yoziladi(self):
        with override_settings(DEBUG=True):
            data = self.client.post(reverse('otp_send'), {'phone': '90 123 45 67'}).json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['phone'], PHONE)
        response = self.client.post(reverse('otp_verify'), {'phone': PHONE, 'code': data['debug_code']}).json()
        self.assertTrue(response['ok'])
        self.assertIn(f'login:{PHONE}', self.client.session['verified_phones'])

    def test_productionda_kod_qaytarilmaydi(self):
        data = self.client.post(reverse('otp_send'), {'phone': PHONE}).json()  # testlarda DEBUG=False
        self.assertNotIn('debug_code', data)

    def test_notogri_raqam(self):
        response = self.client.post(reverse('otp_send'), {'phone': '123'})
        self.assertEqual(response.status_code, 400)


class EskizBackendTests(TestCase):
    @override_settings(SMS_BACKEND='eskiz', ESKIZ_EMAIL='a@b.uz', ESKIZ_PASSWORD='x', SMS_SENDER='4546')
    def test_eskiz_sorovlari(self):
        from django.core.cache import cache
        cache.clear()
        calls = []

        def fake_post(self, path, data, token=None):
            calls.append((path, data, token))
            return {'data': {'token': 'TKN'}} if path == '/auth/login' else {'status': 'waiting'}

        with mock.patch('otp.sms.EskizBackend._post', fake_post):
            services.send_code(PHONE, 'login')
        self.assertEqual(calls[0][0], '/auth/login')
        path, data, token = calls[1]
        self.assertEqual(path, '/message/sms/send')
        self.assertEqual(data['mobile_phone'], '998901234567')
        self.assertEqual(data['from'], '4546')
        self.assertEqual(token, 'TKN')
