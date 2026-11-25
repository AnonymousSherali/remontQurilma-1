"""Promo-kodlar va referal dasturi.

Chegirma platforma hisobidan: mijoz kamroq to'laydi, usta kelishilgan narxni to'liq oladi
(komissiya kelishilgan narxdan hisoblanadi). Shuning uchun:
- chegirma faqat onlayn to'lovda (naqd hisob-kitobda platforma pulni ko'rmaydi);
- chegirma narxning PROMO_MAX_SHARE_PERCENT foizidan oshmaydi va to'lanmagan bosqichlarga
  ulushiga qarab taqsimlanadi;
- kodni faqat birinchi to'lovgacha qo'shish mumkin.

Referal: tasdiqlangan buyurtmadan keyin mijoz shaxsiy kod oladi va do'stiga beradi. Do'st birinchi
buyurtmasida chegirma oladi; do'stning buyurtmasi onlayn to'lanib tasdiqlansa — kod egasiga
mukofot kodi (SMS) beriladi. Usta referali: taklif qilingan usta birinchi ishini bajarsa — bepul TOP.
"""

import secrets
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Milestone, PromoCode, PromoRedemption, Quote
from .plans import PLAN_CASH

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # 0/O, 1/I adashmasligi uchun


class PromoError(Exception):
    pass


def _orders():
    from repair_service.models import ServiceRequest
    return ServiceRequest


def _random_code(prefix, length=6):
    return prefix + ''.join(secrets.choice(ALPHABET) for _i in range(length))


def _unique_code(prefix):
    while True:
        code = _random_code(prefix)
        if not PromoCode.objects.filter(code=code).exists():
            return code


def _active_redemptions(promo):
    SR = _orders()
    return promo.redemptions.exclude(order__status=SR.STATUS_CANCELLED)


def validate(code, phone, order=None):
    """Kodni tekshiradi. Qaytaradi: PromoCode yoki PromoError."""
    code = (code or '').strip().upper()
    if not code:
        raise PromoError(_('Promo-kodni kiriting.'))
    promo = PromoCode.objects.filter(code=code, is_active=True).first()
    now = timezone.now()
    if promo is None or (promo.valid_from and promo.valid_from > now) or (promo.valid_until and promo.valid_until < now):
        raise PromoError(_("Promo-kod topilmadi yoki muddati tugagan."))
    if promo.owner_phone and promo.owner_phone == phone:
        raise PromoError(_("O'z taklif kodingizni ishlata olmaysiz — uni do'stlaringizga bering."))
    if promo.only_phone and promo.only_phone != phone:
        raise PromoError(_("Bu kod boshqa raqam uchun berilgan."))
    used = _active_redemptions(promo)
    if order is not None:
        used = used.exclude(order=order)
    if promo.max_uses is not None and used.count() >= promo.max_uses:
        raise PromoError(_("Bu promo-kodning limiti tugagan."))
    if used.filter(phone=phone).count() >= promo.per_phone_limit:
        raise PromoError(_("Bu promo-kodni allaqachon ishlatgansiz."))
    if promo.first_order_only:
        SR = _orders()
        previous = SR.objects.filter(phone=phone, status__in=(SR.STATUS_COMPLETED, SR.STATUS_CONFIRMED))
        if order is not None:
            previous = previous.exclude(pk=order.pk)
        if previous.exists():
            raise PromoError(_("Bu promo-kod faqat birinchi buyurtma uchun."))
    return promo


def discount_for(promo, total):
    """Kelishilgan narxdan chegirma summasi (butun so'm)."""
    total = Decimal(total)
    if total < promo.min_amount:
        return Decimal(0)
    if promo.kind == PromoCode.KIND_PERCENT:
        value = (total * promo.value / Decimal(100)).quantize(Decimal('1'), rounding=ROUND_DOWN)
    else:
        value = Decimal(promo.value)
    if promo.max_discount is not None:
        value = min(value, promo.max_discount)
    cap = (total * Decimal(settings.PROMO_MAX_SHARE_PERCENT) / Decimal(100)).quantize(Decimal('1'), rounding=ROUND_DOWN)
    return max(Decimal(0), min(value, cap))


def can_apply(order):
    """Kod qo'shish/almashtirish mumkinmi: hech bir bosqich hali to'lanmagan."""
    SR = _orders()
    return (order.status not in (SR.STATUS_CANCELLED, SR.STATUS_CONFIRMED, SR.STATUS_DISPUTED)
            and not order.milestones.exclude(state=Milestone.STATE_PENDING).exists())


@transaction.atomic
def apply(order, code):
    """Buyurtmaga kod qo'llaydi (yoki almashtiradi). Narx kelishilgan bo'lsa — bosqichlarga taqsimlaydi."""
    SR = _orders()
    order = SR.objects.select_for_update().get(pk=order.pk)
    if not can_apply(order):
        raise PromoError(_("Promo-kodni faqat birinchi to'lovgacha qo'shish mumkin."))
    promo = validate(code, order.phone, order)
    redemption, _created = PromoRedemption.objects.update_or_create(
        order=order, defaults={'promo': promo, 'phone': order.phone, 'discount': 0})
    distribute(order)
    redemption.refresh_from_db()
    return redemption


def remove(order):
    if can_apply(order):
        PromoRedemption.objects.filter(order=order).delete()
        order.milestones.filter(state=Milestone.STATE_PENDING).update(discount=0)


def distribute(order):
    """Chegirmani to'lanmagan bosqichlarga summasiga mutanosib taqsimlaydi (narx tasdiqlanganda chaqiriladi)."""
    redemption = PromoRedemption.objects.filter(order=order).select_related('promo').first()
    quote = Quote.objects.filter(order=order, status=Quote.STATUS_APPROVED).first()
    if redemption is None or quote is None:
        return Decimal(0)
    milestones = list(order.milestones.filter(state=Milestone.STATE_PENDING).order_by('position'))
    if quote.plan == PLAN_CASH or not milestones:
        PromoRedemption.objects.filter(pk=redemption.pk).update(discount=0)
        return Decimal(0)
    total = discount_for(redemption.promo, quote.amount)
    base = sum((m.amount for m in milestones), Decimal(0))
    left = total
    for index, milestone in enumerate(milestones):
        share = left if index == len(milestones) - 1 else (total * milestone.amount / base).quantize(
            Decimal('1'), rounding=ROUND_DOWN)
        share = min(share, milestone.amount - 1000)   # har bir to'lov kamida 1000 so'm qoladi
        milestone.discount = max(share, Decimal(0))
        milestone.save(update_fields=['discount'])
        left -= milestone.discount
    applied = total - left
    PromoRedemption.objects.filter(pk=redemption.pk).update(discount=applied)
    return applied


def total_discount(order):
    return sum((m.discount for m in order.milestones.all()), Decimal(0))


# ---------- Referal ----------

def referral_code_for(phone):
    """Mijozning shaxsiy taklif kodi (bir marta yaratiladi)."""
    promo = PromoCode.objects.filter(purpose=PromoCode.PURPOSE_REFERRAL, owner_phone=phone).first()
    if promo is None:
        promo = PromoCode.objects.create(
            code=_unique_code('D'), purpose=PromoCode.PURPOSE_REFERRAL, owner_phone=phone,
            kind=PromoCode.KIND_PERCENT, value=settings.REFERRAL_DISCOUNT_PERCENT,
            max_discount=settings.REFERRAL_MAX_DISCOUNT, first_order_only=True, per_phone_limit=1)
    return promo


def can_refer(phone):
    """Taklif kodi faqat kamida bitta tasdiqlangan buyurtmasi bor mijozga beriladi."""
    SR = _orders()
    return SR.objects.filter(phone=phone, status=SR.STATUS_CONFIRMED).exists()


def on_confirmed(order):
    """Buyurtma tasdiqlandi: referal mukofotlari (mijoz va usta)."""
    _reward_customer_referrer(order)
    _reward_master_referrer(order)


def _reward_customer_referrer(order):
    redemption = (PromoRedemption.objects.filter(order=order, rewarded=False, discount__gt=0,
                                                 promo__purpose=PromoCode.PURPOSE_REFERRAL)
                  .select_related('promo').first())
    if redemption is None or not redemption.promo.owner_phone:
        return None
    with transaction.atomic():
        if not PromoRedemption.objects.filter(pk=redemption.pk, rewarded=False).update(rewarded=True):
            return None
        owner = redemption.promo.owner_phone
        reward = PromoCode.objects.create(
            code=_unique_code('M'), purpose=PromoCode.PURPOSE_REWARD, only_phone=owner, owner_phone='',
            kind=PromoCode.KIND_PERCENT, value=settings.REFERRAL_REWARD_PERCENT,
            max_discount=settings.REFERRAL_REWARD_MAX, max_uses=1, per_phone_limit=1,
            valid_until=timezone.now() + timedelta(days=settings.REFERRAL_REWARD_DAYS))
    from otp.sms import send_sms
    with translation.override(order.language or 'uz'):
        text = _("Do'stingiz siz bergan kod bilan buyurtma qildi. Rahmat! Keyingi buyurtmangizga %(p)s%% chegirma: "
                 "%(code)s (%(days)s kun amal qiladi).") % {
            'p': settings.REFERRAL_REWARD_PERCENT, 'code': reward.code, 'days': settings.REFERRAL_REWARD_DAYS}
    transaction.on_commit(lambda: send_sms(owner, text, background=True))
    return reward


def master_referral_code(master):
    if not master.referral_code:
        from masters.models import Master
        while True:
            code = _random_code('U', 5)
            if not Master.objects.filter(referral_code=code).exists():
                break
        master.referral_code = code
        master.save(update_fields=['referral_code'])
    return master.referral_code


def _reward_master_referrer(order):
    from masters.models import Master

    from .models import Purchase
    from .tariffs import KIND_TOP, activate
    master = order.master
    if master is None or master.referred_by_id is None or master.referral_rewarded or not master.is_verified:
        return None
    if not Master.objects.filter(pk=master.pk, referral_rewarded=False).update(referral_rewarded=True):
        return None
    inviter = master.referred_by
    purchase = Purchase.objects.create(master=inviter, plan='referral', kind=KIND_TOP,
                                       days=settings.MASTER_REFERRAL_TOP_DAYS, amount=0)
    activate(purchase)
    from otp.sms import send_sms
    with translation.override(settings.LANGUAGE_CODE):
        text = _("Siz taklif qilgan usta %(name)s birinchi buyurtmasini bajardi. Sizga %(days)s kun bepul TOP!") % {
            'name': master.full_name, 'days': settings.MASTER_REFERRAL_TOP_DAYS}
    transaction.on_commit(lambda: send_sms(inviter.phone, text, background=True))
    return purchase


def stats():
    """Admin statistikasi uchun: berilgan chegirmalar."""
    used = Milestone.objects.filter(discount__gt=0).exclude(state__in=(Milestone.STATE_PENDING,
                                                                       Milestone.STATE_REFUNDED))
    return sum((m.discount for m in used), Decimal(0))

