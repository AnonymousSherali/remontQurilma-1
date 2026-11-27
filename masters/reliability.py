"""Ustaning ishonchliligi: 0–100 ball, so'nggi RELIABILITY_WINDOW_DAYS kun bo'yicha.

Nimalar hisobga olinadi (usta o'zi ta'sir qila oladigan narsalar):
- voz kechish — qabul qilgan buyurtmalardan qanchasidan voz kechgan        (−35 gacha)
- nizolar — qabul qilgan buyurtmalarning qanchasida nizo ochilgan            (−35 gacha)
- kechikish — belgilangan vaqtdan 30 daqiqadan ko'p kech kelgan yoki kelmagan (−20 gacha)
- javob tezligi — to'g'ridan-to'g'ri buyurtmani qabul qilishgacha (mediana)    (−10 gacha, 4 soatda to'liq)

Buyurtmalar kam bo'lsa (< RELIABILITY_MIN_ORDERS) ball qo'yilmaydi — yangi usta jazolanmaydi.
Qidiruvda: reyting × (0.7 + 0.3 × ball/100), masofa bo'yicha saralashda masofa shu ko'paytuvchiga bo'linadi.
"""

from datetime import timedelta
from statistics import median

from django.conf import settings
from django.utils import timezone

LATE_MINUTES = 30
NO_SHOW_HOURS = 2
RESPONSE_FULL_PENALTY_MIN = 240


def _settings():
    return (getattr(settings, 'RELIABILITY_WINDOW_DAYS', 90), getattr(settings, 'RELIABILITY_MIN_ORDERS', 3))


def compute(master, now=None):
    from repair_service.models import OrderEvent, ServiceRequest as SR
    now = now or timezone.now()
    window, min_orders = _settings()
    since = now - timedelta(days=window)
    events = OrderEvent.objects.filter(master=master, actor=OrderEvent.ACTOR_MASTER, created_at__gte=since)

    # Faqat haqiqiy "qabul qildi" o'tishlari (oldingi yozuv boshqa holatda bo'lgan): shu holatdagi
    # boshqa yozuvlar (tashrif vaqti, rasm, izoh) hisoblanmaydi
    feed_notes = ('Lentadan olindi', 'Взят из ленты')
    candidate_orders = set(events.filter(status=SR.STATUS_ACCEPTED).values_list('order_id', flat=True))
    accept_ids, previous = [], {}
    for pk, order_id, status, event_master, actor, created in (
            OrderEvent.objects.filter(order_id__in=candidate_orders).order_by('created_at', 'pk')
            .values_list('pk', 'order_id', 'status', 'master_id', 'actor', 'created_at')):
        if (status == SR.STATUS_ACCEPTED and previous.get(order_id) != SR.STATUS_ACCEPTED
                and event_master == master.pk and actor == OrderEvent.ACTOR_MASTER and created >= since):
            accept_ids.append(pk)
        previous[order_id] = status
    accept_events = list(OrderEvent.objects.filter(pk__in=accept_ids).select_related('order'))
    accepted = len(accept_events)
    declined = events.filter(status=SR.STATUS_NEW).count()
    # Nizo va kechikish — faqat hozir shu ustada turgan buyurtmalar (voz kechgandan keyingisi boshqa ustaniki)
    order_ids = set(SR.objects.filter(pk__in={e.order_id for e in accept_events}, master=master)
                    .values_list('pk', flat=True))
    disputes = (OrderEvent.objects.filter(order_id__in=order_ids, status=SR.STATUS_DISPUTED)
                .values('order').distinct().count())

    # Kechikish: belgilangan vaqtli tashriflar
    late = scheduled = 0
    for order in SR.objects.filter(pk__in=order_ids, visit_at__isnull=False, visit_at__lte=now):
        arrived = (order.events.filter(status=SR.STATUS_ARRIVED).order_by('created_at')
                   .values_list('created_at', flat=True).first())
        if arrived is None:
            if order.status == SR.STATUS_CANCELLED or now < order.visit_at + timedelta(hours=NO_SHOW_HOURS):
                continue    # mijoz bekor qilgan yoki hali erta
            scheduled += 1
            late += 1       # kelmagan
            continue
        scheduled += 1
        if arrived > order.visit_at + timedelta(minutes=LATE_MINUTES):
            late += 1

    # Javob tezligi: faqat ustaga to'g'ridan-to'g'ri kelgan buyurtmalar (lentadan olish — bir zumda)
    minutes = [(e.created_at - e.order.created_at).total_seconds() / 60 for e in accept_events
               if e.note not in feed_notes and e.created_at >= e.order.created_at]
    response = round(median(minutes)) if minutes else None

    data = {'accepted': accepted, 'declined': declined, 'disputes': disputes, 'late': late,
            'scheduled': scheduled, 'response_minutes': response, 'window_days': window}
    if accepted + declined < min_orders:
        return None, data
    decline_rate = declined / (accepted + declined)
    dispute_rate = min(disputes / max(accepted, 1), 1)
    late_rate = late / scheduled if scheduled else 0
    response_penalty = min(response or 0, RESPONSE_FULL_PENALTY_MIN) / RESPONSE_FULL_PENALTY_MIN
    score = 100 - 35 * decline_rate - 35 * dispute_rate - 20 * late_rate - 10 * response_penalty
    data.update({'decline_rate': round(decline_rate * 100), 'dispute_rate': round(dispute_rate * 100),
                 'on_time_rate': round((1 - late_rate) * 100) if scheduled else None})
    return max(0, min(100, round(score))), data


def update(master, now=None):
    from .models import Master
    score, data = compute(master, now)
    if (score, data) != (master.reliability, master.reliability_data):
        # queryset.update — post_save signallari (bonus va h.k.) har soat behuda ishlamasin
        Master.objects.filter(pk=master.pk).update(reliability=score, reliability_data=data)
    master.reliability, master.reliability_data = score, data
    return score


FULL_RECOMPUTE_HOUR = 3   # har kuni shu soatda — barchasi (eskirgan voqealar oynadan chiqadi)


def update_all(now=None, full=None):
    """Har soat: faqat oxirgi 2 soatda voqeasi bo'lgan yoki tashrifi o'tgan ustalar; kuniga bir marta — hammasi."""
    from repair_service.models import OrderEvent, ServiceRequest as SR

    from .models import Master
    now = now or timezone.now()
    if full is None:
        full = timezone.localtime(now).hour == FULL_RECOMPUTE_HOUR
    masters = Master.objects.filter(is_verified=True)
    if not full:
        recent = now - timedelta(hours=2)
        active = set(OrderEvent.objects.filter(created_at__gte=recent, master__isnull=False)
                     .values_list('master_id', flat=True))
        # Kelmaganlik NO_SHOW_HOURS dan keyin aniqlanadi — o'sha paytga to'g'ri kelgan tashriflar
        active |= set(SR.objects.filter(visit_at__gte=recent - timedelta(hours=NO_SHOW_HOURS),
                                        visit_at__lte=now, master__isnull=False)
                      .values_list('master_id', flat=True))
        masters = masters.filter(pk__in=active)
    count = 0
    for master in masters:
        update(master, now)
        count += 1
    return count


def tips(master):
    """Kabinet uchun: ballni oshirish bo'yicha maslahatlar."""
    from django.utils.translation import gettext as _
    data = master.reliability_data or {}
    result = []
    if data.get('decline_rate', 0) >= 15:
        result.append(_("Buyurtmani faqat albatta bora olsangiz qabul qiling — voz kechish ballni ko'p tushiradi."))
    if data.get('on_time_rate') is not None and data['on_time_rate'] < 90:
        result.append(_("Kelish vaqtini real belgilang; kechiksangiz, mijozga yozib vaqtni o'zgartiring."))
    if (data.get('response_minutes') or 0) > 60:
        result.append(_("Yangi buyurtmaga tezroq javob bering — Telegram yoki bildirishnomalarni yoqing."))
    if data.get('dispute_rate', 0) >= 10:
        result.append(_("Narx va ish hajmini oldindan aniq kelishing, ishdan oldin va keyin rasmga oling."))
    return result
