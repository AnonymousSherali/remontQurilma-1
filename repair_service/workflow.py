"""Buyurtma bosqichlari: buyurtmachi va usta statuslarni navbat bilan belgilaydi.

    01 Buyurtmachi  Buyurtma yaratildi
    02 Usta         Qabul qilindi
    03 Usta         Joyida
    04 Usta         Ishda
    05 Usta         Bajarildi
    06 Buyurtmachi  Tasdiqlandi

Bosqichlarni sakrab o'tib bo'lmaydi: "Joyida"siz "Ishda" bo'lmaydi. Har bir
o'tish OrderEvent'ga yoziladi — ikkala tomon ham bir xil tarixni ko'radi.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .models import OrderEvent, ServiceRequest as SR

CUSTOMER = OrderEvent.ACTOR_CUSTOMER
MASTER = OrderEvent.ACTOR_MASTER
ADMIN = OrderEvent.ACTOR_ADMIN
SYSTEM = OrderEvent.ACTOR_SYSTEM

# Timeline'dagi 6 qadam: (holat, kim belgilaydi, nomi, tavsifi)
STEPS = [
    (SR.STATUS_NEW, CUSTOMER, gettext_lazy('Buyurtma yaratildi'),
     gettext_lazy('Vazifa, manzil va qulay vaqtni tasvirlaysiz.')),
    (SR.STATUS_ACCEPTED, MASTER, gettext_lazy('Qabul qilindi'),
     gettext_lazy('Usta ishni olishini tasdiqlaydi.')),
    (SR.STATUS_ARRIVED, MASTER, gettext_lazy('Joyida'),
     gettext_lazy("Usta kelganini belgilaydi — buni buyurtmada darhol ko'rasiz.")),
    (SR.STATUS_IN_PROGRESS, MASTER, gettext_lazy('Ishda'),
     gettext_lazy("Ish haqiqatan boshlanganda status o'zgaradi.")),
    (SR.STATUS_COMPLETED, MASTER, gettext_lazy('Bajarildi'),
     gettext_lazy("Usta o'z tomonidan buyurtmani yopadi.")),
    (SR.STATUS_CONFIRMED, CUSTOMER, gettext_lazy('Tasdiqlandi'),
     gettext_lazy('Siz natijani tekshirasiz, tasdiqlaysiz va baholaysiz.')),
]

# (kim, amal) -> (qaysi holatlardan, yangi holat, tugma matni)
TRANSITIONS = {
    (MASTER, 'accept'): ({SR.STATUS_NEW}, SR.STATUS_ACCEPTED, gettext_lazy('Qabul qilish')),
    (MASTER, 'arrive'): ({SR.STATUS_ACCEPTED}, SR.STATUS_ARRIVED, gettext_lazy('Joyga yetib keldim')),
    (MASTER, 'start'): ({SR.STATUS_ARRIVED}, SR.STATUS_IN_PROGRESS, gettext_lazy('Ishni boshladim')),
    (MASTER, 'complete'): ({SR.STATUS_IN_PROGRESS}, SR.STATUS_COMPLETED, gettext_lazy('Ish bajarildi')),
    # Usta kelib bo'lgach bir tomonlama bekor qila olmaydi — faqat nizo orqali
    # "Bekor qilish" emas, voz kechish: buyurtma lentaga qaytadi (release_to_feed)
    (MASTER, 'cancel'): ({SR.STATUS_NEW, SR.STATUS_ACCEPTED}, SR.STATUS_NEW, gettext_lazy('Voz kechish')),

    (CUSTOMER, 'confirm'): ({SR.STATUS_COMPLETED}, SR.STATUS_CONFIRMED, gettext_lazy('Natijani tasdiqlash')),
    (CUSTOMER, 'cancel'): ({SR.STATUS_NEW, SR.STATUS_ACCEPTED}, SR.STATUS_CANCELLED, gettext_lazy('Buyurtmani bekor qilish')),
    (CUSTOMER, 'dispute'): ({SR.STATUS_ARRIVED, SR.STATUS_IN_PROGRESS, SR.STATUS_COMPLETED}, SR.STATUS_DISPUTED,
                            gettext_lazy('Muammo bor (nizo ochish)')),
}


class WorkflowError(Exception):
    pass


def available_actions(order, actor):
    return [
        (action, label) for (who, action), (sources, _target, label) in TRANSITIONS.items()
        if who == actor and order.status in sources
    ]


def next_master_action(order):
    """Ustaning asosiy (keyingi) tugmasi — bekor qilishdan tashqari."""
    for action, label in available_actions(order, MASTER):
        if action != 'cancel':
            return action, label
    return None


def record(order, status, actor, note=''):
    return OrderEvent.objects.create(order=order, status=status, actor=actor, note=note[:500])


@transaction.atomic
def apply(order, actor, action, note=''):
    """Holatni o'zgartiradi. Qoidaga zid bo'lsa WorkflowError."""
    from payments import services as payments

    order = SR.objects.select_for_update().get(pk=order.pk)
    if actor == MASTER and action == 'cancel':
        return release_to_feed(order, note)
    key = (actor, action)
    if key not in TRANSITIONS:
        raise WorkflowError(_("Noma'lum amal"))
    sources, target, _label = TRANSITIONS[key]
    if order.status not in sources:
        raise WorkflowError(_("Bu amalni hozirgi bosqichda bajarib bo'lmaydi"))
    if actor == MASTER and action != 'cancel' and order.master_id is None:
        raise WorkflowError(_('Buyurtmaga usta biriktirilmagan'))

    # Ish narx kelishilmaguncha boshlanmaydi (naqd reja bo'lsa ham — narx yozma qayd etilsin)
    if target == SR.STATUS_IN_PROGRESS and not payments.quote_approved(order):
        raise WorkflowError(_("Ishni boshlashdan oldin narxni taklif qiling va mijoz rozi bo'lsin"))

    # Eskrou: bosqichga tegishli qism to'lanmaguncha o'tib bo'lmaydi
    unpaid = payments.unfunded_for(order, target)
    if unpaid:
        names = ', '.join(m.title for m in unpaid)
        if actor == CUSTOMER:
            raise WorkflowError(_('Avval to\'lang: %(names)s') % {'names': names})
        raise WorkflowError(_("Mijoz hali to'lamagan: %(names)s. To'lovdan keyin davom eting.") % {'names': names})

    order.status = target
    order.save(update_fields=['status', 'updated_at'])
    record(order, target, actor, note)

    if target == SR.STATUS_CONFIRMED:
        payments.release_on_confirm(order)

    from .customer_notify import notify_status_change
    transaction.on_commit(lambda: notify_status_change(order, actor))
    return order


def release_to_feed(order, note=''):
    """Usta buyurtmadan voz kechdi: buyurtma bekor bo'lmaydi, boshqa ustalar uchun lentaga qaytadi."""
    from payments.models import Milestone, Quote

    sources = TRANSITIONS[(MASTER, 'cancel')][0]
    if order.status not in sources or order.master_id is None:
        raise WorkflowError(_("Bu amalni hozirgi bosqichda bajarib bo'lmaydi"))
    if order.milestones.exclude(state=Milestone.STATE_PENDING).exists():
        raise WorkflowError(_("Mijoz to'lov qilgan — voz kechish uchun administratorga murojaat qiling"))
    master = order.master
    Quote.objects.filter(order=order).delete()  # narx shu usta bilan kelishilgan edi
    order.milestones.all().delete()
    order.declined_by.add(master)
    order.master = None
    order.status = SR.STATUS_NEW
    order.open_since = timezone.now()
    order.save(update_fields=['master', 'status', 'open_since', 'updated_at'])
    record(order, SR.STATUS_NEW, MASTER, note or _('Usta voz kechdi: %(name)s') % {'name': master.full_name})

    from .customer_notify import notify_open_order, notify_status_change
    transaction.on_commit(lambda: notify_status_change(order, MASTER))
    transaction.on_commit(lambda: notify_open_order(order))
    return order


def admin_set_status(order, status, note=''):
    """Admin istalgan holatga o'tkaza oladi (nizo hal qilish va h.k.) — tarixga yoziladi."""
    record(order, status, ADMIN, note)


def auto_confirm(now=None):
    """Usta "Bajarildi" degandan keyin mijoz AUTO_CONFIRM_HOURS davomida javob bermasa — tasdiqlanadi."""
    now = now or timezone.now()
    hours = getattr(settings, 'AUTO_CONFIRM_HOURS', 72)
    done = []
    for order in SR.objects.filter(status=SR.STATUS_COMPLETED):
        completed_at = (
            order.events.filter(status=SR.STATUS_COMPLETED).order_by('-created_at')
            .values_list('created_at', flat=True).first()
        ) or order.updated_at
        if now - completed_at < timedelta(hours=hours):
            continue
        try:
            apply(order, CUSTOMER, 'confirm', note=_('Avtomatik: mijoz %(h)s soat ichida javob bermadi') % {'h': hours})
        except WorkflowError:
            continue  # masalan, oxirgi qism to'lanmagan — admin ko'rib chiqadi
        OrderEvent.objects.filter(order=order, status=SR.STATUS_CONFIRMED).update(actor=SYSTEM)
        done.append(order)
    return done


def timeline(order):
    """Timeline uchun 6 qadam: holati (done/current/upcoming) va vaqti."""
    times = {}
    for event in order.events.all():
        times.setdefault(event.status, event.created_at)
    times.setdefault(SR.STATUS_NEW, order.created_at)

    flow_index = SR.FLOW.index(order.status) if order.status in SR.FLOW else None
    # Nizo yoki bekor: oxirgi erishilgan bosqichgacha "done"
    if flow_index is None:
        reached = [SR.FLOW.index(s) for s in times if s in SR.FLOW]
        flow_index = max(reached) if reached else 0

    steps = []
    for index, (status, actor, title, description) in enumerate(STEPS):
        if index < flow_index or (index == flow_index and order.status == SR.STATUS_CONFIRMED):
            state = 'done'
        elif index == flow_index:
            state = 'current' if order.status in SR.FLOW else 'stopped'
        else:
            state = 'upcoming'
        steps.append({
            'n': f'{index + 1:02d}', 'status': status, 'actor': actor, 'title': title,
            'description': description, 'state': state, 'at': times.get(status),
        })
    # Progress chizig'i: 0..100% (birinchi va oxirgi nuqta orasida)
    progress = round(flow_index / (len(STEPS) - 1) * 100)
    return {'steps': steps, 'progress': progress}


def showcase_timeline():
    """Bosh sahifa uchun: holatsiz, faqat qadamlar."""
    return {
        'steps': [
            {'n': f'{i + 1:02d}', 'status': s, 'actor': a, 'title': t, 'description': d, 'state': 'static', 'at': None}
            for i, (s, a, t, d) in enumerate(STEPS)
        ],
        'progress': 100,
    }
