"""Ustalarga pul o'tkazish usullari (provayderlar).

Hozir — «manual»: tizim haftalik ro'yxatni tayyorlaydi, administrator bank yoki to'lov tizimi
kabinetidan o'tkazadi va «O'tkazildi» deb belgilaydi.

Avtomatik o'tkazma (to'lov tizimining kartaga to'lash — payout xizmati) uchun alohida shartnoma
va API hujjati kerak. Hujjat qo'lga kelgach, shu fayldagi PayoutProvider dan voris yozing,
`send()` ni amalga oshiring va PAYOUT_PROVIDER=<nom> qiling — qolgan hamma narsa (jadval,
xabarlar, hisobot) o'zgarmaydi.
"""

from django.conf import settings


class PayoutProvider:
    name = 'base'

    def send(self, payout):
        """O'tkazmani boshlaydi. Qaytaradi: (holat, tashqi_raqam, xato_matni).

        holat: 'paid' — pul ketdi; 'prepared' — admin qo'lda o'tkazishi kerak; 'failed' — xato.
        """
        raise NotImplementedError


class ManualProvider(PayoutProvider):
    name = 'manual'

    def send(self, payout):
        return 'prepared', '', ''


PROVIDERS = {'manual': ManualProvider}


def get_provider():
    return PROVIDERS.get(getattr(settings, 'PAYOUT_PROVIDER', 'manual'), ManualProvider)()
