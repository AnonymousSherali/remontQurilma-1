"""Bazani namunaviy ma'lumotlar bilan to'ldirish.

Ishlatish:
    python manage.py seed_demo
    python manage.py seed_demo --reset   # avval eskilarini o'chiradi
"""

from django.core.management.base import BaseCommand
from repair_service.models import Service, Brand, Testimonial


SERVICES = [
    ('Ustani chaqirish', 0, 'Ta\'mirlash holatida ustaning chiqishi bepul.', 1),
    ('Kir yuvish mashinasini diagnostika qilish', 0, 'Ta\'mirlash buyurtma qilinsa — bepul.', 2),
    ('Diagnostika (ta\'mirlamasdan)', 50000, 'To\'liq diagnostika va muammoni aniqlash.', 3),
    ('Kichik ta\'mir (bitta detal almashtirish)', 100000, 'Bitta detalni almashtirish bilan ta\'mirlash.', 4),
    ('O\'rtacha ta\'mir', 200000, 'Bir nechta tugun va detallarni ta\'mirlash.', 5),
    ('Kapital ta\'mir', 300000, 'To\'liq qismlarga ajratish bilan kapital ta\'mir.', 6),
]

BRANDS = [
    'Zanussi', 'Indesit', 'Bosch', 'Samsung', 'LG', 'Ariston', 'Beko', 'Candy',
    'Electrolux', 'Whirlpool', 'Siemens', 'Hansa', 'Vestel', 'Haier', 'AEG', 'Neff',
]

TESTIMONIALS = [
    ('Dilshod Rahimov', 'Mashina suvni chiqarmay qolgandi. Usta o\'sha kuni keldi va bir soatda tuzatdi. Narxi ham oldindan aytilgani kabi bo\'ldi.', 5),
    ('Nodira Karimova', 'Telefon qilganimdan keyin ikki soatda usta yetib keldi. Nasosni almashtirdi, ishi toza. Rahmat!', 5),
    ('Jasur To\'rayev', 'Diagnostika bepul bo\'ldi, muammoni tushuntirib berishdi. Detal kutishga to\'g\'ri keldi, lekin natija yaxshi.', 4),
    ('Malika Yusupova', 'Podshipnik almashtirishdi. Mashina yangidek ishlayapti, shovqin ham yo\'qoldi.', 5),
    ('Sardor Aliyev', 'Kechqurun chaqirdim, dam olish kuni bo\'lishiga qaramay kelishdi. Xizmat sifatli.', 5),
    ('Zulfiya Ergasheva', 'Boshqa joyda "yangisini oling" deyishgandi. Bu yerda ta\'mirlab berishdi va ancha arzon tushdi.', 5),
]


class Command(BaseCommand):
    help = "Bazani namunaviy xizmatlar, brendlar va sharhlar bilan to'ldiradi"

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help="Yangilarini qo'shishdan oldin mavjud xizmat/brend/sharhlarni o'chiradi",
        )

    def handle(self, *args, **options):
        if options['reset']:
            Service.objects.all().delete()
            Brand.objects.all().delete()
            Testimonial.objects.all().delete()
            self.stdout.write(self.style.WARNING("Eski ma'lumotlar o'chirildi."))

        created = 0
        for name, price, description, order in SERVICES:
            _, is_new = Service.objects.get_or_create(
                name=name,
                defaults={'price_from': price, 'description': description, 'order': order},
            )
            created += is_new
        self.stdout.write(f"Xizmatlar: {created} ta yangi qo'shildi.")

        created = 0
        for order, name in enumerate(BRANDS, start=1):
            _, is_new = Brand.objects.get_or_create(name=name, defaults={'order': order})
            created += is_new
        self.stdout.write(f"Brendlar: {created} ta yangi qo'shildi.")

        created = 0
        for client_name, text, rating in TESTIMONIALS:
            _, is_new = Testimonial.objects.get_or_create(
                client_name=client_name,
                defaults={'text': text, 'rating': rating},
            )
            created += is_new
        self.stdout.write(f"Sharhlar: {created} ta yangi qo'shildi.")

        self.stdout.write(self.style.SUCCESS("Namunaviy ma'lumotlar tayyor."))
