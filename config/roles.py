"""Admin xodimlari uchun tayyor rollar (guruhlar). `python manage.py setup_roles` yaratadi/yangilaydi.

Xodimga rol berish: Admin → Foydalanuvchilar → xodim → «Xodim» belgisi + «Guruhlar».
Superuser hamma narsani ko'radi; boshqalar faqat o'z guruhi huquqlarini.
"""

V, C, A, D = 'view', 'change', 'add', 'delete'

ROLES = {
    # Mijoz va ustalar bilan ishlaydi: arizalar, yordam chati, ustalarni tekshirish, kafolat
    'Operator': {
        'repair_service.servicerequest': (V,),
        'repair_service.orderevent': (V,),
        'repair_service.ordermessage': (V,),
        'repair_service.orderphoto': (V,),
        'repair_service.supportthread': (V, C),
        'repair_service.supportmessage': (V,),
        'repair_service.warrantyclaim': (V, C),
        'repair_service.npsresponse': (V,),
        'masters.master': (V, C),
        'masters.masterdocument': (V, C),
        'masters.review': (V, C),
        'masters.category': (V,),
    },
    # Nizolar sahifasi: dalillarni ko'radi va qaror qabul qiladi (ushlab turilgan pul taqdiri)
    'Nizo hakami': {
        'repair_service.servicerequest': (V, C),
        'repair_service.orderevent': (V,),
        'repair_service.ordermessage': (V,),
        'repair_service.orderphoto': (V,),
        'repair_service.warrantyclaim': (V, C),
        'payments.quote': (V,),
        'payments.milestone': (V,),
        'payments.payment': (V,),
        'payments.refund': (V,),
        'masters.master': (V,),
    },
    # Pul: ustalarga o'tkazmalar, qaytarishlar, bank o'tkazmalari, tariflar, statistika
    'Moliyachi': {
        'payments.payout': (V, C),
        'payments.milestone': (V, C),
        'payments.payment': (V, C),
        'payments.refund': (V, C),
        'payments.purchase': (V, C),
        'payments.quote': (V,),
        'payments.promocode': (V,),
        'payments.promoredemption': (V,),
        'repair_service.servicerequest': (V,),
        'masters.master': (V,),
    },
    # Aksiyalar, promo-kodlar, kontent, A/B testlar
    'Marketolog': {
        'repair_service.campaign': (V, C, A),
        'repair_service.campaigndelivery': (V,),
        'repair_service.marketingconsent': (V,),
        'repair_service.experiment': (V, C, A),
        'repair_service.testimonial': (V, C, A, D),
        'repair_service.brand': (V, C, A),
        'repair_service.service': (V, C, A),
        'repair_service.npsresponse': (V,),
        'payments.promocode': (V, C, A),
        'payments.promoredemption': (V,),
        'payments.payment': (V,),      # statistika sahifasi
        'masters.category': (V, C),
        'masters.lesson': (V, C, A),
    },
}


def setup():
    """Guruhlarni yaratadi va huquqlarini ROLES bilan aynan bir xil qiladi. Qaytaradi: {nom: huquqlar soni}."""
    from django.contrib.auth.models import Group, Permission

    result = {}
    for name, models in ROLES.items():
        perms = []
        for label, actions in models.items():
            app_label, model = label.split('.')
            for action in actions:
                perms.append(Permission.objects.get(content_type__app_label=app_label,
                                                    codename=f'{action}_{model}'))
        group, _created = Group.objects.get_or_create(name=name)
        group.permissions.set(perms)
        result[name] = len(perms)
    return result
