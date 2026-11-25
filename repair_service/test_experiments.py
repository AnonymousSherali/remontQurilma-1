from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from . import experiments
from .models import AnalyticsEvent, Experiment, ExperimentExposure
from .tests import AJAX, VALID

UA = {'HTTP_USER_AGENT': 'Mozilla/5.0 (Linux; Android 14) Chrome/130'}


class ExperimentTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')

    def test_test_yoq_bolsa_hozirgi_variant(self):
        self.assertEqual(experiments.assign('ariza_tugmasi', 'abc'), 'a')
        self.assertContains(self.client.get('/', **UA), 'Ariza yuborish')
        self.assertFalse(ExperimentExposure.objects.exists())

    def test_taqsimlash_barqaror_va_teng(self):
        Experiment.objects.create(key='ariza_tugmasi', name='Tugma', is_active=True)
        variants = [experiments.assign('ariza_tugmasi', f'{i:016x}') for i in range(2000)]
        self.assertEqual(variants, [experiments.assign('ariza_tugmasi', f'{i:016x}') for i in range(2000)])
        self.assertTrue(900 < variants.count('b') < 1100)

    @override_settings(REQUEST_RATE_LIMIT=100)   # 12 ta tashrifchi bitta IP'dan — spam chegarasi xalaqit bermasin
    def test_sahifada_va_natijalar(self):
        exp = Experiment.objects.create(key='ariza_tugmasi', name='Tugma', is_active=True)
        seen = {'a': 0, 'b': 0}
        for i in range(12):
            client = self.client_class()
            body = client.get('/', **UA).content.decode()
            variant = 'b' if 'Usta chaqirish — bepul' in body else 'a'
            seen[variant] += 1
            if variant == 'b':
                client.post(reverse('repair_service:submit_request'), {**VALID, 'phone': f'+99890000{i:04d}'},
                            **UA, **AJAX)
        self.assertEqual(ExperimentExposure.objects.count(), 12)
        rows = {r['variant']: r for r in experiments.results(exp)}
        self.assertEqual(rows['a']['visitors'], seen['a'])
        self.assertEqual(rows['b']['requests'], seen['b'])
        self.assertEqual(rows['a']['requests'], 0)
        self.assertFalse(rows['b']['significant'])                        # 100 tadan kam — xulosa yo'q

    def test_golib(self):
        Experiment.objects.create(key='ariza_tugmasi', name='Tugma', is_active=True, winner='b')
        self.assertContains(self.client.get('/', **UA), 'Usta chaqirish — bepul')
        self.assertFalse(ExperimentExposure.objects.exists())

    def test_dnt_qatnashmaydi(self):
        Experiment.objects.create(key='ariza_tugmasi', name='Tugma', is_active=True)
        self.assertContains(self.client.get('/', HTTP_DNT='1', **UA), 'Ariza yuborish')
        self.assertFalse(ExperimentExposure.objects.exists())

    def test_z_test(self):
        self.assertLess(experiments._z_test(50, 1000, 90, 1000), 0.01)
        self.assertGreater(experiments._z_test(50, 1000, 52, 1000), 0.5)
        self.assertIsNone(experiments._z_test(0, 0, 1, 10))

    def test_admin(self):
        exp = Experiment.objects.create(key='ariza_tugmasi', name='Tugma', is_active=True)
        ExperimentExposure.objects.create(experiment=exp, visitor='v1', variant='a')
        AnalyticsEvent.objects.create(name='request', visitor='v1', path='/')
        self.client.force_login(User.objects.create_superuser('a', 'a@example.com', 'x'))
        page = self.client.get(reverse('admin:repair_service_experiment_change', args=[exp.pk]))
        self.assertContains(page, '100.0%')
