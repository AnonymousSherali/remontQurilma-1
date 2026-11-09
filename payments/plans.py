"""To'lov rejalari: kelishilgan summa qaysi bosqichda qanday qismlarga bo'linadi.

Har bir qism (milestone) uchun `release_status` — buyurtma shu holatga yetganda
mablag' ustaga chiqariladi. Usta shu holatni belgilashdan oldin mijoz o'sha
qismni to'lagan (platformada ushlab turilgan) bo'lishi shart — Upwork'dagi
"milestone"lar va YouDo'dagi "Сделка без риска" bilan bir xil g'oya.
"""

from decimal import ROUND_DOWN, Decimal

from django.utils.translation import gettext_lazy as _

PLAN_CASH = 'cash'
PLAN_ON_COMPLETION = 'on_completion'
PLAN_ADVANCE = 'advance_30'
PLAN_THIRDS = 'thirds'

# (foiz, nomi, qaysi holatda chiqariladi)
PLANS = {
    PLAN_ON_COMPLETION: [
        (Decimal('100'), _("To'liq summa — tasdiqlangandan keyin"), 'confirmed'),
    ],
    PLAN_ADVANCE: [
        (Decimal('30'), _('Avans (materiallar uchun) — ish boshlanganda'), 'in_progress'),
        (Decimal('70'), _('Qolgan qism — tasdiqlangandan keyin'), 'confirmed'),
    ],
    PLAN_THIRDS: [
        (None, _('1-qism — ish boshlanganda'), 'in_progress'),
        (None, _('2-qism — ish bajarilganda'), 'completed'),
        (None, _('3-qism — tasdiqlangandan keyin'), 'confirmed'),
    ],
    PLAN_CASH: [],
}

PLAN_CHOICES = [
    (PLAN_ON_COMPLETION, _("Ish yakunida to'liq (pul oldindan platformada ushlab turiladi)")),
    (PLAN_ADVANCE, _('30% avans + 70% yakunda')),
    (PLAN_THIRDS, _('3 teng qism: boshlanganda / bajarilganda / tasdiqlanganda')),
    (PLAN_CASH, _("Naqd yoki to'g'ridan-to'g'ri ustaga (platforma kafolatisiz)")),
]


def split_amount(total, plan):
    """Summani reja bo'yicha qismlarga bo'ladi. Tiyin yo'qolmasligi uchun qoldiq oxirgi qismga."""
    total = Decimal(total)
    parts = PLANS[plan]
    if not parts:
        return []
    amounts = []
    for percent, title, status in parts[:-1]:
        share = (total / len(parts)) if percent is None else (total * percent / 100)
        amounts.append((share.quantize(Decimal('1'), rounding=ROUND_DOWN), title, status))
    last_title, last_status = parts[-1][1], parts[-1][2]
    amounts.append((total - sum(a for a, _, _ in amounts), last_title, last_status))
    return amounts
