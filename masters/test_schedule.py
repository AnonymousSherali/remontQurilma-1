from datetime import date, time, timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from repair_service import workflow
from repair_service.models import ServiceRequest
from repair_service.tests import make_master

from . import feed, schedule
from .models import Category, DayOff
from .services import search_masters

# 2026-11-25 — chorshanba
WED_10 = timezone.make_aware(timezone.datetime(2026, 11, 25, 10, 0))
WED_21 = timezone.make_aware(timezone.datetime(2026, 11, 25, 21, 0))
SAT_10 = timezone.make_aware(timezone.datetime(2026, 11, 28, 10, 0))


class ScheduleTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        self.master = make_master('Usta', '+998911111111', work_days=[0, 1, 2, 3, 4],
                                  work_from=time(8, 0), work_to=time(20, 0))

    def test_ish_vaqti(self):
        self.assertTrue(schedule.is_working(self.master, WED_10))
        self.assertFalse(schedule.is_working(self.master, WED_21))
        self.assertFalse(schedule.is_working(self.master, SAT_10))
        self.assertEqual(schedule.summary(self.master), 'Du–Ju 08:00–20:00')
        self.assertEqual(schedule.status_label(self.master, WED_10), '')
        self.assertEqual(schedule.status_label(self.master, WED_21), 'Hozir ishlamaydi — ertaga 08:00 dan')
        self.assertIn('08:00', schedule.status_label(self.master, SAT_10))          # dushanba 08:00
        self.assertEqual(schedule.next_working_start(self.master, SAT_10).weekday(), 0)

    def test_jadvalsiz_usta_doim_ishlaydi(self):
        free = make_master('Erkin', '+998922222222')
        self.assertTrue(schedule.is_working(free, WED_21))
        self.assertEqual(schedule.summary(free), '')

    def test_dam_olish_qidiruv_va_lenta(self):
        today = timezone.localdate()
        cat = Category.objects.create(name='Santexnik', slug='santexnik')
        self.master.categories.add(cat)
        self.master.work_days, self.master.work_from, self.master.work_to = [], None, None
        self.master.save()
        self.assertIn(self.master, search_masters(category=cat))
        DayOff.objects.create(master=self.master, start=today, end=today + timedelta(days=3))
        self.assertNotIn(self.master, search_masters(category=cat))
        self.assertFalse(feed.can_work(self.master))
        self.assertEqual(schedule.status_label(self.master), 'Dam olishda')
        self.master.telegram_chat_id = 5
        self.master.save()
        order = ServiceRequest.objects.create(name='A', phone='+998901112233', category=cat,
                                              latitude='41.3', longitude='69.25')
        self.assertNotIn(self.master, feed.nearby_masters(order))

    def test_kabinet_sahifasi(self):
        self.client.force_login(self.master.user)
        url = reverse('masters:work_schedule')
        self.assertContains(self.client.get(url), 'Ish kunlari')
        self.client.post(url, {'work_days': [0, 1, 2, 3, 4, 5], 'work_from': '09:00', 'work_to': '18:00'})
        self.master.refresh_from_db()
        self.assertEqual((self.master.work_days, self.master.work_from), ([0, 1, 2, 3, 4, 5], time(9, 0)))
        self.client.post(url, {'work_days': [0], 'work_from': '18:00', 'work_to': '09:00'})   # noto'g'ri
        self.master.refresh_from_db()
        self.assertEqual(self.master.work_days, [0, 1, 2, 3, 4, 5])
        self.client.post(url, {'work_days': list(range(7)), 'work_from': '', 'work_to': ''})
        self.master.refresh_from_db()
        self.assertEqual((self.master.work_days, self.master.work_from), ([], None))     # har kuni

        start = timezone.localdate() + timedelta(days=1)
        self.client.post(url, {'form': 'off', 'start': start, 'end': start + timedelta(days=2), 'note': "Ta'til"})
        off = DayOff.objects.get()
        self.client.post(url, {'form': 'off', 'start': date(2020, 1, 1), 'end': date(2020, 1, 2)})   # o'tgan sana
        self.assertEqual(DayOff.objects.count(), 1)
        self.client.post(url, {'delete': off.pk})
        self.assertFalse(DayOff.objects.exists())

    def test_profil_va_kelish_vaqti_ogohlantirishi(self):
        self.assertContains(self.client.get(self.master.get_absolute_url()), 'Du–Ju 08:00–20:00')
        order = ServiceRequest.objects.create(name='A', phone='+998901112233', master=self.master)
        workflow.apply(order, workflow.MASTER, 'accept')
        self.client.force_login(self.master.user)
        day = timezone.localdate() + timedelta(days=1)
        response = self.client.post(reverse('masters:visit_set', args=[order.pk]),
                                    {'date': day.isoformat(), 'time': '22:30'}, follow=True)
        self.assertContains(response, 'ish jadvalingizdan tashqarida')
