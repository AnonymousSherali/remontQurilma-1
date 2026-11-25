"""Ustalar uchun o'quv bo'limi: darslar, video, «o'qidim» belgisi, boshlang'ich kurs."""

import re

from django.conf import settings
from django.utils.formats import date_format
from django.utils.translation import get_language

YOUTUBE_RE = re.compile(r'(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})')


def youtube_embed(url):
    """Faqat YouTube; youtube-nocookie.com — reklama cookie'larisiz."""
    match = YOUTUBE_RE.search(url or '')
    return f'https://www.youtube-nocookie.com/embed/{match.group(1)}' if match else ''


def placeholders():
    from payments.payouts import next_payout_date
    weekday = date_format(next_payout_date(), 'l')
    return {
        'komissiya': f'{settings.PLATFORM_FEE_PERCENT:g}', 'pro_komissiya': f'{settings.PRO_FEE_PERCENT:g}',
        'kafolat_kun': settings.WARRANTY_DAYS, 'tasdiq_soat': settings.AUTO_CONFIRM_HOURS,
        'chiqarish_soat': settings.AUTO_RELEASE_HOURS, 'tolov_kuni': weekday,
        'min_tolov': f'{settings.PAYOUT_MIN_AMOUNT:,}'.replace(',', ' '),
    }


def render_text(lesson):
    """Joriy tildagi matn, o'rinbosarlar sozlamalardan (matn tizim bilan doim mos)."""
    ru = (get_language() or '').startswith('ru')
    text = lesson.body_ru if ru and lesson.body_ru else lesson.body
    values = placeholders()
    return re.sub(r'\{(\w+)\}', lambda m: str(values.get(m.group(1), m.group(0))), text)


def title(lesson):
    ru = (get_language() or '').startswith('ru')
    return lesson.title_ru if ru and lesson.title_ru else lesson.title


def progress(master):
    from .models import Lesson
    required = list(Lesson.objects.filter(is_published=True, is_required=True).values_list('pk', flat=True))
    done = set(master.lessons_done.values_list('lesson_id', flat=True))
    finished = len([pk for pk in required if pk in done])
    return {'done': finished, 'total': len(required), 'complete': finished >= len(required),
            'percent': round(finished * 100 / len(required)) if required else 100, 'done_ids': done}
