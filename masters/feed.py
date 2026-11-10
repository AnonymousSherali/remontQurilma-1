"""Ochiq buyurtmalar lentasi: ustasi biriktirilmagan buyurtmalarni ustalar o'zlari oladi.

Kimga ko'rinadi: tasdiqlangan, "buyurtma qabul qilaman" holatidagi ustaga — o'z
yo'nalishi bo'yicha va xizmat radiusi ichidagi buyurtmalar (joylashuvsiz buyurtmalar
yo'nalish bo'yicha hammaga). Voz kechgan buyurtmasi qayta ko'rsatilmaydi.

Maxfiylik: lentada mijozning ismi, telefoni va aniq manzili YO'Q — faqat tuman,
masofa va muammo tavsifi. Ular ustaga buyurtmani olgandan keyin ochiladi.

PRO ustunligi: yangi buyurtmani dastlabki FEED_PRO_HEAD_START_MINUTES daqiqada faqat
PRO ustalar ola oladi.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from payments import tariffs
from repair_service import workflow
from repair_service.models import ServiceRequest as SR

from .geo import haversine_km
from .locations import district_name


class FeedError(Exception):
    pass


def head_start():
    return timedelta(minutes=getattr(settings, 'FEED_PRO_HEAD_START_MINUTES', 10))


def available_from(order, master):
    """Shu usta buyurtmani qaysi vaqtdan ola oladi (PRO — darhol)."""
    opened = order.open_since or order.created_at
    return opened if master.is_pro else opened + head_start()


def can_work(master):
    return master.is_verified and master.is_available and master.user.is_active


def _base_queryset(master):
    return (
        SR.objects.filter(master__isnull=True, status=SR.STATUS_NEW)
        .filter(Q(category__in=master.categories.all()) | Q(category__isnull=True))
        .exclude(declined_by=master)
        .select_related('category', 'catalog_item').distinct()
    )


def _annotate(order, master):
    """Masofa va lentada ko'rsatiladigan hudud. Radiusdan tashqarida bo'lsa None qaytaradi."""
    order.distance_km = None
    if order.latitude is not None:
        distance = haversine_km(master.latitude, master.longitude, order.latitude, order.longitude)
        if distance > master.service_radius_km:
            return None
        order.distance_km = round(distance, 1)
    order.area = district_name(order.district)
    order.claimable_from = available_from(order, master)
    order.claimable = order.claimable_from <= timezone.now()
    return order


def open_orders(master, limit=50):
    if not can_work(master):
        return []
    orders = [o for o in (_annotate(o, master) for o in _base_queryset(master).order_by('-created_at')[:200]) if o]
    # Yaqinlari birinchi; joylashuvi noma'lumlar oxirida
    orders.sort(key=lambda o: (o.distance_km is None, o.distance_km or 0, -o.created_at.timestamp()))
    return orders[:limit]


def open_count(master):
    return len(open_orders(master))


def active_count(master):
    return master.requests.filter(status__in=[SR.STATUS_ACCEPTED, SR.STATUS_ARRIVED, SR.STATUS_IN_PROGRESS]).count()


@transaction.atomic
def claim(master, order_id):
    """Usta buyurtmani oladi. Ikki usta bir vaqtda bossa — faqat birinchisi oladi."""
    if not can_work(master):
        raise FeedError(_("Buyurtma olish uchun profilingiz tasdiqlangan va «buyurtma qabul qilaman» holatida bo'lishi kerak"))
    order = SR.objects.select_for_update().filter(pk=order_id).first()
    if order is None or order.master_id is not None or order.status != SR.STATUS_NEW:
        raise FeedError(_('Bu buyurtmani boshqa usta olib bo\'ldi'))
    if not _base_queryset(master).filter(pk=order.pk).exists() or _annotate(order, master) is None:
        raise FeedError(_('Bu buyurtma sizning yo\'nalishingiz yoki hududingizga to\'g\'ri kelmaydi'))
    if not order.claimable:
        raise FeedError(_("Dastlabki daqiqalarda buyurtmani faqat PRO ustalar oladi. Siz %(time)s dan ola olasiz.") % {
            'time': timezone.localtime(order.claimable_from).strftime('%H:%M')})
    limit = tariffs.active_orders_limit(master)
    if active_count(master) >= limit:
        raise FeedError(_("Sizda %(n)s ta faol buyurtma bor — avval ularni yakunlang") % {'n': limit})

    order.master = master
    order.save(update_fields=['master', 'updated_at'])
    return workflow.apply(order, workflow.MASTER, 'accept', note=_('Lentadan olindi'))


def nearby_masters(order, limit=30):
    """Yangi ochiq buyurtma haqida xabar beriladigan ustalar (Telegram ulanganlar)."""
    from .models import Master
    qs = Master.objects.public().filter(is_available=True, telegram_chat_id__isnull=False).exclude(
        pk__in=order.declined_by.values('pk'))
    if order.category_id:
        qs = qs.filter(categories=order.category_id)
    result = []
    for master in qs.distinct():
        if _annotate(order, master) is not None:
            result.append((order.distance_km if order.distance_km is not None else 9999, master))
    result.sort(key=lambda pair: (not pair[1].is_pro, pair[0]))
    return [m for _d, m in result[:limit]]
