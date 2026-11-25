from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from repair_service.tests import make_master

from . import learning
from .models import Lesson, LessonProgress


class LearningTests(TestCase):
    def setUp(self):
        cache.clear()
        translation.activate('uz')
        self.master = make_master('Usta', '+998911111111')
        self.client.force_login(self.master.user)

    def tearDown(self):
        translation.activate('uz')

    def test_boshlangich_darslar_va_progress(self):
        self.assertEqual(Lesson.objects.count(), 6)                         # migratsiya bilan
        self.assertContains(self.client.get(reverse('masters:dashboard')), 'ich kurs: 0/6')
        lessons = list(Lesson.objects.all())
        response = self.client.post(reverse('masters:lesson', args=[lessons[0].slug]))
        self.assertRedirects(response, reverse('masters:lesson', args=[lessons[1].slug]))
        for lesson in lessons[1:]:
            self.client.post(reverse('masters:lesson', args=[lesson.slug]))
        self.assertTrue(learning.progress(self.master)['complete'])
        self.assertNotContains(self.client.get(reverse('masters:dashboard')), 'ich kurs:')
        self.client.post(reverse('masters:lesson', args=[lessons[0].slug]))     # takror — xato emas
        self.assertEqual(LessonProgress.objects.count(), 6)

    @override_settings(PLATFORM_FEE_PERCENT=12.0, WARRANTY_DAYS=45)
    def test_orinbosarlar_sozlamalardan(self):
        text = self.client.get(reverse('masters:lesson', args=['narx-va-tolov'])).content.decode()
        self.assertIn('Komissiya — 12%', text)
        self.assertNotIn('{komissiya}', text)
        self.assertContains(self.client.get(reverse('masters:lesson', args=['nizo-kafolat-ball'])), '45 kun kafolat')
        self.assertContains(self.client.get('/ru' + reverse('masters:lesson', args=['narx-va-tolov'])), 'Комиссия — 12%')

    def test_video_faqat_youtube(self):
        self.assertEqual(learning.youtube_embed('https://youtu.be/dQw4w9WgXcQ'),
                         'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
        self.assertEqual(learning.youtube_embed('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10'),
                         'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
        self.assertEqual(learning.youtube_embed('https://evil.com/video'), '')
        lesson = Lesson.objects.first()
        lesson.video_url = 'https://youtu.be/dQw4w9WgXcQ'
        lesson.save()
        self.assertContains(self.client.get(reverse('masters:lesson', args=[lesson.slug])), 'youtube-nocookie.com/embed/')

    def test_yashirin_dars_va_mehmon(self):
        lesson = Lesson.objects.first()
        lesson.is_published = False
        lesson.save()
        self.assertEqual(self.client.get(reverse('masters:lesson', args=[lesson.slug])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('masters:lessons')).status_code, 302)
