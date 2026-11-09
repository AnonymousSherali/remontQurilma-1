"""O'zbekiston telefon raqamlari bilan ishlash.

Raqam bazada yagona ko'rinishda saqlanadi: "+998901234567". Shunda bir xil
raqamni turli formatda yozilgani uchun ikki xil deb hisoblash xatosi bo'lmaydi
(masalan, takroriy ro'yxatdan o'tishni tekshirishda).
"""

import re

from django.core.exceptions import ValidationError

PHONE_ERROR = "Telefon raqamini to'g'ri kiriting: +998 (XX) XXX-XX-XX"


def normalize_phone(value):
    """Har qanday yozilishni "+998XXXXXXXXX" ga keltiradi yoki ValidationError beradi.

    Qabul qilinadi: "+998 (90) 123-45-67", "998901234567", "90 123 45 67".
    """
    digits = re.sub(r'\D', '', value or '')
    if len(digits) == 9:
        digits = '998' + digits
    if len(digits) != 12 or not digits.startswith('998'):
        raise ValidationError(PHONE_ERROR)
    return '+' + digits


def format_phone(value):
    """"+998901234567" -> "+998 90 123-45-67". Noma'lum formatni o'zgartirmaydi."""
    digits = re.sub(r'\D', '', value or '')
    if len(digits) != 12 or not digits.startswith('998'):
        return value or ''
    return f'+998 {digits[3:5]} {digits[5:8]}-{digits[8:10]}-{digits[10:12]}'
