# TechService — uy ustalari platformasi

Santexnik, elektrik, kir yuvish mashinasi, konditsioner va boshqa maishiy
yo'nalishlardagi ustalarni **joylashuv bo'yicha** topish, **ariza qoldirish**
va **mezonlar bo'yicha baholash** platformasi. Django 5.2 LTS.

## Imkoniyatlar

**Mijozlar uchun**
- Yo'nalish + joylashuv bo'yicha eng yaqin ustalar (brauzer geolokatsiyasi yoki Toshkent tumani)
- Masofa yoki reyting bo'yicha saralash, radius tanlash, xaritada ko'rish
- Usta profili: tajriba, hudud, 4 mezon bo'yicha baholar, mijozlar izohlari
- Aniq ustaga yoki umumiy ariza — ustasiz ariza yaqin atrofdagi ustalarning **ochiq buyurtmalar lentasiga** tushadi
- Tasdiqlangan ishga **kafolat** (standart 30 kun): muammo qaytalansa, usta bepul tuzatadi
- Ish tugagach maxsus havola orqali baholash: **ish sifati, o'z vaqtida kelishi, narx adolatliligi, muomala madaniyati**

**Ustalar uchun**
- Telefon raqam bilan ro'yxatdan o'tish, yo'nalishlar, ish hududi (GPS / tuman / xaritada belgilash), xizmat radiusi
- Kabinet: kelgan arizalar, holatni o'zgartirish (qabul → bajarildi / bekor), baho havolasini nusxalash yoki Telegram orqali yuborish
- "Band" rejimi — vaqtincha qidiruvdan yashirinish
- Ochiq buyurtmalar lentasi (`/kabinet/ochiq/`) — mos buyurtmani birinchi bo'lib olish
- Tariflar (`/kabinet/tarif/`): TOP joylashuv va PRO obuna

**Administrator uchun** (`/admin/`, django-unfold dizayni)
- Boshqaruv paneli: yangi arizalar, tasdiq kutayotgan ustalar, 7 kunlik grafik, so'nggi arizalar
- Ustalarni tasdiqlash / yashirish, arizaga usta biriktirish, baholarni moderatsiya qilish
- Yangi ariza haqida Telegram xabari (ixtiyoriy)

## Narxlar katalogi

`/narxlar/` — platforma narxlari (Urban Company tajribasi): yo'nalish bo'yicha filtr,
qidiruv (o'zbek va rus tilida), har bir xizmat uchun:

- **qat'iy narx** yoki **"...dan"**, birlik (xizmat / dona / metr / m² / nuqta / soat);
- **taxminiy vaqt** ("~40 daqiqa") va **narxga nima kiradi** ro'yxati;
- "Buyurtma berish" — xizmat tanlangan holda ariza (miqdor bilan), taxminiy summa
  buyurtmada saqlanadi va ustaga ko'rinadi.

Usta narx taklif qilganda katalog narxi oldindan to'ldiriladi. Taklif katalogdan
**20% dan ko'p farq qilsa, sababini yozish majburiy**, mijoz esa "katalogdan 35% qimmat"
belgisini ko'radi. Katalog admin'da: **Sayt kontenti → Narxlar** (ruscha nomlar,
"Ommabop" belgisi bosh sahifaga chiqaradi). Namunaviy 27 ta xizmat: `seed_demo`.

## Ish rasmlari

- **Mijoz** buyurtma sahifasida muammo rasmini yuklaydi (SMS-tasdiqdan keyin) — usta
  kerakli ehtiyot qismni oldindan biladi.
- **Usta** "Oldin" va "Keyin" rasmlarini yuklaydi (buyurtmani qabul qilgandan keyin).
  Ish boshlanmagan bo'lsa "Oldin", boshlangan bo'lsa "Keyin" avtomatik tanlanadi.
- Tasdiqlangan buyurtmalarning "oldin/keyin" juftliklari ustaning ommaviy profilida
  **"Bajarilgan ishlar"** bo'limiga chiqadi. Mijoz buyurtma sahifasida buni o'chira oladi;
  admin nomaqbul rasmni "Ish rasmlari" bo'limida yashiradi (buyurtmada dalil sifatida qoladi).
- Xavfsizlik: faqat haqiqiy JPG/PNG/WEBP (Pillow bilan tekshiriladi), 10 MB gacha, bir
  tomonga 12 ta; **EXIF butunlay o'chiriladi** (telefon rasmidagi GPS — mijozning uy
  manzili), 1600 px gacha kichraytiriladi, fayl nomlari tasodifiy.
- Nizo ochilgan yoki tasdiqlangan buyurtmada rasmni o'chirib bo'lmaydi — dalil saqlanadi;
  lekin qo'shimcha rasm yuklash mumkin.

> Eslatma: rasmlar `media/` orqali beriladi. Fayl nomlari taxmin qilib bo'lmaydigan,
> lekin havolani bilgan odam rasmni ko'ra oladi. Kerak bo'lsa keyinroq rasmlarni
> faqat buyurtma ishtirokchilariga beradigan himoyalangan ko'rinishga o'tkazish mumkin.

## Buyurtma bosqichlari

Buyurtmachi va usta statuslarni **navbat bilan** belgilaydi; ikkalasi ham bir xil
timeline'ni ko'radi (bosh sahifada namunasi, buyurtma sahifalarida jonli holati).

| # | Kim | Holat | Shart |
|---|---|---|---|
| 01 | Buyurtmachi | Buyurtma yaratildi | — |
| 02 | Usta | Qabul qilindi | — |
| 03 | Usta | Joyida | — |
| 04 | Usta | Ishda | narx kelishilgan + shu bosqich qismi to'langan |
| 05 | Usta | Bajarildi | shu bosqich qismi to'langan (3 qismli rejada) |
| 06 | Buyurtmachi | Tasdiqlandi | oxirgi qism to'langan; baho bilan birga |

- Bosqichni sakrab o'tib bo'lmaydi; har bir o'tish vaqti bilan tarixga yoziladi.
- Usta joyga kelgach bir tomonlama bekor qila olmaydi; buyurtmachi esa faqat
  "Muammo bor" (nizo) ocha oladi — pul muzlatiladi, admin hal qiladi.
- Usta "Bajarildi" deganidan keyin buyurtmachi 72 soat javob bermasa, buyurtma
  avtomatik tasdiqlanadi (`AUTO_CONFIRM_HOURS`).

## Bosqichma-bosqich to'lov (eskrou)

Upwork'dagi *milestone*lar va YouDo'dagi "Сделка без риска" g'oyasi:

1. Usta narx va to'lov rejasini taklif qiladi; mijoz SMS-tasdiq bilan rozi bo'ladi.
2. Rejalar: **yakunda 100%**, **30% avans + 70%**, **3 teng qism**
   (boshlanganda / bajarilganda / tasdiqlanganda) yoki **naqd** (platforma kafolatisiz).
3. Mijoz to'lagan pul ustaga emas, platformada **ushlab turiladi**. Usta tegishli
   bosqichni faqat shu qism to'langandan keyin belgilay oladi — bepul ishlamaydi.
4. Bosqichga yetilgach mijoz "Bosqichni tasdiqlab, to'lash" ni bosadi yoki 48 soatdan
   keyin avtomatik chiqariladi (`AUTO_RELEASE_HOURS`). Nizo ochilsa — hech narsa chiqmaydi.
5. Platforma komissiyasi `PLATFORM_FEE_PERCENT` (standart 10%). Ustaga o'tkazilgan
   pullar admin'da "Ustaning kartasiga o'tkazildi" deb belgilanadi.

To'lov tizimlari: `PAYMENT_PROVIDERS=payme,click,uzum` — mijoz har bir bosqichni Payme, Click
yoki Uzum Bank bilan to'lashni tanlaydi. `demo` — sinov sahifasi (faqat `DEBUG=True` da).

| Tizim | Manzil (kabinetda ko'rsatiladi) |
|---|---|
| Payme Merchant API | `/payments/payme/` (hisob maydoni: `milestone_id`) |
| Click Shop API | `/payments/click/prepare/` va `/payments/click/complete/` |
| Uzum Bank Merchant API | `/payments/uzum/check/`, `create/`, `confirm/`, `reverse/`, `status/` (Basic auth) |

**Payme va Click integratsiyalari protokol testlari bilan qoplangan, lekin haqiqiy sinov
muhitida (Payme sandbox, Click test vositasi) tekshirilmagan** — ishga tushirishdan oldin
o'sha yerdagi barcha testlardan o'tkazing.

> ⚠️ **Uzum Bank** integratsiyasi (`payments/uzum.py`) rasmiy hujjatga qaramasdan, protokolning
> umumiy tuzilishi bo'yicha yozilgan (Uzum hujjati faqat shartnoma tuzgan hamkorlarga beriladi).
> Maydon nomlari, xato kodlari va to'lov sahifasi havolasi farq qilishi mumkin — Uzum bergan
> hujjat bilan solishtirib, to'g'rilamaguncha `PAYMENT_PROVIDERS` ga `uzum` ni qo'shmang.

Avtomatik tasdiqlash va chiqarish uchun cron (har soatda):

```bash
5 * * * *  cd /srv/techservice/app && /srv/techservice/venv/bin/python manage.py process_orders   # to'liq ro'yxat: deploy/cron.txt
```

> ⚖️ Platforma hisobida boshqa shaxs (usta) uchun pul ushlab turish to'lov
> xizmatlari bo'yicha qonunchilikka (ZRU-578 "To'lovlar va to'lov tizimlari
> to'g'risida") tegishli bo'lishi mumkin. Ishga tushirishdan oldin yurist bilan
> agentlik shartnomasi yoki litsenziyalangan to'lov tashkilotining "xavfsiz bitim"
> xizmatidan foydalanish masalasini aniqlang.

## SMS tasdiqlash

`otp` ilovasi: 6 xonali kod, 5 daqiqa amal qiladi, 5 ta urinish, bir raqamga
60 soniyada 1 / soatiga 5 ta, bir IP'dan soatiga 20 ta. Kod bazada xesh holida.

Qayerda ishlatiladi: usta ro'yxatdan o'tishi, ustaning parolni tiklashi,
buyurtmachining "Mening buyurtmalarim"ga kirishi va buyurtmadagi har qanday amal
(narxga rozilik, to'lov, tasdiqlash, bekor qilish). Buyurtma havolasi faqat
**ko'rish** imkonini beradi — havola begona qo'lga tushsa ham pul harakatlanmaydi.

`SMS_BACKEND=console` — kod server konsoliga chiqadi (va `DEBUG=True` da sahifada
ko'rsatiladi). `SMS_BACKEND=eskiz` — Eskiz.uz orqali haqiqiy SMS. Eskiz SMS
matnlarini shablon sifatida oldindan moderatsiyadan o'tkazishni talab qiladi.

Xabarnomalar: mijozga — ariza qabul qilinganda (kuzatish havolasi bilan), usta
qabul qilganda, yetib kelganda, ishni yakunlaganda, narx taklif qilganda; ustaga —
yangi buyurtma, mijoz tasdiqlaganda yoki nizo ochganda.

## Ochiq buyurtmalar lentasi

Mijoz usta tanlamay ariza qoldirsa (formada tuman yoki geolokatsiya ixtiyoriy), buyurtma
yo'nalishi va xizmat radiusi mos keladigan tasdiqlangan ustalarga ko'rinadi — saytda
`/kabinet/ochiq/` va Telegram'da «✋ Olish» tugmasi bilan. Birinchi olgan usta bajaradi.

- Lentada mijozning **ismi, telefoni va aniq manzili ko'rinmaydi** — faqat tuman, masofa,
  muammo tavsifi va rasmlar. To'liq ma'lumot buyurtma olingach ochiladi.
- PRO ustalar yangi buyurtmani `FEED_PRO_HEAD_START_MINUTES` (10) daqiqa oldin oladi.
- Bir vaqtdagi faol buyurtmalar cheklangan: `ACTIVE_ORDERS_LIMIT` (5), PRO — `PRO_ACTIVE_ORDERS_LIMIT` (10).
- Usta joyga kelguncha **voz kechsa**, buyurtma bekor bo'lmaydi — lentaga qaytadi va boshqa
  ustalarga taklif qilinadi (voz kechgan ustaga qayta ko'rsatilmaydi). Mijoz to'lov qilgan
  bo'lsa, voz kechish faqat administrator orqali.

## Tariflar (ustalar uchun)

Platformadan foydalanish bepul; tariflar — ixtiyoriy. To'lov o'sha Payme/Click/Uzum orqali.

| Tarif | Nima beradi | Namunaviy narx |
|---|---|---|
| TOP 7 / 30 kun | Qidiruvda yo'nalish bo'yicha birinchi qatorlar, «TOP» belgisi | 50 000 / 150 000 so'm |
| PRO 30 kun | Komissiya 10% o'rniga 5%, lentada ustunlik, ko'proq faol buyurtma, «PRO» belgisi | 200 000 so'm |

**Narxlar namunaviy** — `.env` da `TARIFF_TOP_7_PRICE`, `TARIFF_TOP_30_PRICE`,
`TARIFF_PRO_30_PRICE`, `PRO_FEE_PERCENT` orqali o'zgartiring. TOP ustalar «TOP» belgisi bilan
ko'rsatiladi (pullik joylashuv ekani yashirilmaydi). Admin tarifni qo'lda ham faollashtira oladi.

## Kafolat

Buyurtma tasdiqlangan kundan `WARRANTY_DAYS` (30) kun davomida mijoz buyurtma sahifasidan
kafolat murojaati ochishi mumkin (SMS bilan tasdiqlangan raqam, rasm qo'shsa bo'ladi):

1. Murojaat ustaga boradi — usta **bepul** tuzatib, «Tuzatdim» deb belgilaydi.
2. Mijoz «Muammo hal bo'ldi» deydi — murojaat yopiladi (`WARRANTY_AUTO_CLOSE_DAYS` kun javob
   bermasa, o'zi yopiladi).
3. Natija yoqmasa yoki usta `WARRANTY_RESPONSE_HOURS` (48) soat javob bermasa — mijoz
   murojaatni administratorga o'tkazadi. Administrator (`/admin/` → Kafolat murojaatlari) rad
   etadi yoki kompensatsiya belgilaydi.

Kompensatsiya faqat **platforma orqali to'langan** buyurtmalarga, to'langan summa va
`GUARANTEE_MAX_AMOUNT` dan oshmaydi; pulni mijozga administrator qo'lda o'tkazadi, tizimda
qayd qilinadi. Naqd to'langan ishda faqat ustani qayta yuborish mumkin. Katalogdagi har bir
xizmatga alohida muddat qo'yish mumkin («Kafolat (kun)»; 0 — kafolatsiz).

**Muddat, kompensatsiya chegarasi va ustadan qaytarib olish tartibi — biznes qarori**; bu
yerdagi qiymatlar namunaviy, ommaviy oferta matnida aniq yozilishi kerak.

## Kelish vaqti va taqvim

Mijoz arizada qulay kun va oraliqni tanlaydi (ixtiyoriy: «Imkon qadar tez» / bugun…+6 kun,
ertalab / kunduzi / kechqurun / kech). Usta buyurtmani qabul qilgach buyurtma sahifasida
**aniq kelish vaqtini** belgilaydi — mijoz xabar oladi, kabinetda «Taqvim» bloki paydo bo'ladi
(kunlar bo'yicha tashriflar, vaqti belgilanmagan buyurtmalar, yaqin vaqtga ikki buyurtma
tushsa ogohlantirish). Tashrifdan `VISIT_REMINDER_HOURS` (2) soat oldin ikkala tomonga
eslatma boradi — buni `process_orders` cron buyrug'i yuboradi.

## Yozishma (chat)

Buyurtma sahifasida mijoz va usta yozishadi — telefon qilmasdan savol berish, vaqtni aniqlash.

- Faqat ustasi bor, bekor qilinmagan buyurtmada; tasdiqlangach yana `CHAT_OPEN_DAYS` (30) kun ochiq.
- Mijoz tomoni SMS kod bilan tasdiqlangan bo'lishi shart (havolaning o'zi yozishmani ochmaydi).
- Yangi xabar haqida: Telegram ulangan bo'lsa har bir xabar matni bilan, aks holda SMS —
  `CHAT_SMS_INTERVAL_MINUTES` (30) da ko'pi bilan bitta va matnsiz (SMS pullik).
- Sahifa 8 soniyada yangi xabarlarni so'raydi (WebSocket yo'q — oddiy hosting yetarli); JS'siz ham ishlaydi.
- Administrator yozishmani buyurtma sahifasida (`/admin/`) ko'radi — bu chat ostida ochiq yozilgan.

## Ustalarga pul o'tkazish hisoboti

Eskroudan chiqarilgan pul ustaga tegishli, lekin platforma hisobida turadi. `/admin/` →
**Ustalarga to'lanishi kerak**:

1. Har bir usta bo'yicha yig'indi: mijozlar to'lagan summa, komissiya, o'tkaziladigan summa, karta.
2. **Excel** tugmasi ro'yxatni `.xlsx` qilib yuklaydi (bankka topshiriqnoma uchun).
3. Pulni bank yoki to'lov tizimi orqali o'tkazgach, ustalarni belgilab «O'tkazildi» ni bosasiz —
   har bir usta uchun o'tkazma yozuvi yaratiladi (**O'tkazmalar tarixi**, Excel eksport bilan).

Usta kartasini kabinetda «Profil → Pul olish» da kiritadi; kartasi yo'q ustani belgilab
bo'lmaydi. **Tizim pulni o'zi o'tkazmaydi** — bu hisob-kitob vositasi. Avtomatik o'tkazma
uchun to'lov tizimining «payout» xizmati bilan alohida shartnoma kerak.

## Statistika

`/admin/statistika/` — 7 / 30 / 90 kun / 1 yil bo'yicha: voronka (ariza → qabul → bajarildi →
tasdiqlandi), konversiya, o'rtacha chek, aylanma, platforma daromadi (komissiya + tariflar),
qabul qilish tezligi, bekor qilish, nizo va kafolat murojaatlari ulushi, yo'nalishlar va eng
faol ustalar. Ko'rsatkichlar tanlangan davrda **yaratilgan** arizalar bo'yicha hisoblanadi.

## Oferta va maxfiylik siyosati

`/oferta/` va `/maxfiylik/` (ruscha: `/ru/...`). Matndagi raqamlar (komissiya, muddatlar,
kafolat) sozlamalardan olinadi, shuning uchun tizim bilan doim mos turadi.

> ⚠️ **Bu matnlar — namunaviy loyiha, yurist tekshirmagan.** Sahifalarda «Loyiha»
> ogohlantirishi chiqadi. Yurist tasdiqlagach `.env` da `LEGAL_DRAFT=False` qiling va
> `SITE_LEGAL_NAME`, `SITE_LEGAL_INN`, `SITE_LEGAL_ADDRESS` ni to'ldiring.
> Ma'lumotlarni qayerda saqlash — «Production» bo'limidagi eslatmaga qarang.

## Shaxsni tasdiqlash (ustalar)

Usta kabinetda «🪪 Hujjatlar» (`/kabinet/hujjatlar/`) sahifasida pasport/ID-karta va hujjat bilan
selfi yuklaydi (sertifikat — ixtiyoriy). Administrator `/admin/` → Ustalar → usta sahifasida
rasmlarni ko'radi va holatni «Tasdiqlangan» yoki «Rad etilgan» (sababi bilan) qiladi —
usta SMS/Telegram xabar oladi. Tasdiqlanganda profil ham faollashadi va saytda
«🪪 Hujjatlari tekshirilgan» belgisi chiqadi. Ro'yxatda «Hujjatlarni tasdiqlash» ommaviy amali bor.

- Fayllar `PRIVATE_MEDIA_ROOT` da — `MEDIA_ROOT` dan tashqarida, nginx ularni bermaydi, ochiq
  havolasi yo'q. Ko'rish faqat admin sahifasi orqali va faqat **«Can view usta hujjati»**
  huquqi bor xodimga (superuser'dan tashqari bu huquqni alohida bering).
- Rasmdan EXIF (GPS) o'chiriladi, fayl nomi tasodifiy.
- `ID_DOCUMENTS_KEEP_DAYS=N` — tasdiqlangandan N kun o'tgach fayllar o'chiriladi (holat saqlanadi).
  Standart 0 — saqlanadi; muddatni yurist bilan belgilang.

> ⚠️ Hujjat bilan selfi (yuz tasviri) qonunchilikda **biometrik ma'lumot** hisoblanishi mumkin —
> u holda uni faqat O'zbekiston hududidagi serverda saqlash talab qilinadi (pastdagi
> «Production» eslatmasi). Yurist bilan aniqlang; kerak bo'lsa selfini so'ramang yoki
> `PRIVATE_MEDIA_ROOT` ni mahalliy serverga qo'ying.

## Ustani qayta chaqirish

Tasdiqlangan buyurtma sahifasida va «Mening buyurtmalarim» ro'yxatida «🔁 Shu ustani qayta
chaqirish» tugmasi chiqadi (SMS kod bilan tasdiqlangan raqamga). Ism, telefon, manzil va
joylashuv avvalgi buyurtmadan olinadi — mijoz faqat muammoni va qulay vaqtni yozadi; buyurtma
to'g'ridan-to'g'ri o'sha ustaga boradi. Usta band yoki saytda bo'lmasa — shu yo'nalishdagi
boshqa ustalar ro'yxatiga yo'naltiriladi.

## SEO

- **Yo'nalish va tuman sahifalari:** `/ustalar/santexnik/`, `/ustalar/santexnik/chilonzor/`
  (ruscha `/ru/...`) — sarlavha, tavsif, ustalar soni, o'rtacha baho, katalog narxlari,
  qo'shni tumanlar va boshqa yo'nalishlarga havolalar. Ustasi yo'q sahifa `noindex`.
- **`/sitemap.xml`** — statik sahifalar, ustasi bor yo'nalish/tuman sahifalari va usta
  profillari, ikki tilda (`hreflang`, `x-default`). Google Search Console va Yandex Webmaster'ga
  shu manzilni qo'shing.
- **`/robots.txt`** — kabinet, buyurtma, to'lov va API sahifalari yopiq; shaxsiy koordinatali
  qidiruv (`?lat=`) indekslanmaydi. Sinov serverida `SEO_DISALLOW_ALL=True` — butun sayt yopiladi.
- `canonical`: filtrli qidiruv (`/ustalar/?category=santexnik&district=chilonzor`) toza manzilga ishora qiladi.
- **JSON-LD:** Organization va WebSite (bosh sahifa), BreadcrumbList va ItemList (yo'nalish
  sahifalari), usta profili (`HomeAndConstructionBusiness`, baho bilan; telefon va aniq manzilsiz).
- **Open Graph / Twitter:** Telegram va boshqa ilovalarda havola rasm bilan ochiladi
  (`static/img/og.png`; sayt nomini o'zgartirsangiz, rasmni ham almashtiring; usta profilida — usta rasmi).
- Footer'da barcha yo'nalishlarga ichki havolalar.

## Viloyatlar

Toshkentning 12 tumani va barcha viloyatlar (Qoraqalpog'iston bilan) bo'yicha 28 ta shahar — viloyat
markazlari va yirik shaharlar (Chirchiq, Olmaliq, Qo'qon, Marg'ilon, Shahrisabz, Xiva va boshqalar) — qidiruv,
ariza formasi, usta ro'yxatdan o'tishi va SEO sahifalarida (`/ustalar/santexnik/samarqand/`). Tanlov ro'yxatlari
viloyatlar bo'yicha guruhlangan. Yangi shahar qo'shish: `masters/locations.py` →
`REGIONS` dagi viloyatga bitta qator (slug, o'zbekcha, ruscha nomi, kenglik, uzunlik).

## Nizolar (administrator)

`/admin/nizolar/` — ochiq nizolar (eng eskisi yuqorida, muzlatilgan summa, necha kun). Nizo sahifasida
hamma dalil bitta joyda: mijoz va usta (qo'ng'iroq havolasi bilan), mijoz yozgan sabab, narx va
to'lov bosqichlari, yozishma, rasmlar, buyurtma tarixi. Qaror:

- **har bir ushlab turilgan bosqich** bo'yicha: ustaga chiqarish yoki mijozga qaytarish (qisman ham
  mumkin). Biror qism ustaga — buyurtma «Tasdiqlandi», hammasi mijozga — «Bekor qilindi»;
- **«Kelishildi — ish davom etadi»** — buyurtma nizodan oldingi holatiga qaytadi, pul muzlatilgan holicha.

Ikkala tomon qaror izohini SMS/Telegram'da oladi. Mijoz nizoni faqat sababini yozib ochadi;
administrator chatiga Telegram xabari keladi. Qaror uchun «arizani o'zgartirish» huquqi kerak.
Qaytarilgan pulni to'lov tizimi kabinetidan qaytarish kerak — tizim faqat qayd etadi.

## Ustalar ishonchliligi

Har bir ustaga so'nggi 90 kun bo'yicha 0–100 ball (`masters/reliability.py`):
voz kechish (−35 gacha), nizolar (−35), kechikish yoki kelmaslik (−20; belgilangan vaqtdan
30 daqiqa kech), javob tezligi (−10; to'g'ridan-to'g'ri buyurtmani qabul qilishgacha, mediana).
Kam buyurtmali (`RELIABILITY_MIN_ORDERS`, 3) yangi usta jazolanmaydi.

- Qidiruvda reyting `0.7 + 0.3 × ball/100` ga ko'paytiriladi; masofa bo'yicha saralashda ham
  ishonchsiz usta pastroqqa tushadi; ochiq buyurtma xabarlari ham shu tartibda.
- Usta kabinetida ball, ko'rsatkichlar va uni oshirish bo'yicha maslahatlar.
- Profilda: «⚡ Odatda ~15 daqiqada javob beradi», «🕒 O'z vaqtida keladi: 96%».
- `process_orders` (cron) har soatda yangilaydi; voz kechganda darhol.

## Promo-kodlar va referal

**Promo-kod** (admin → To'lovlar → Promo-kodlar): foiz yoki qat'iy summa, eng ko'p chegirma, eng kam
buyurtma, muddat, umumiy va bitta raqamga limit, «faqat birinchi buyurtma».

- Chegirma **platforma hisobidan**: mijoz kamroq to'laydi, usta kelishilgan narxni to'liq oladi
  (komissiya kelishilgan narxdan). Faqat onlayn to'lovda, narxning `PROMO_MAX_SHARE_PERCENT` (50%)
  foizigacha; to'lanmagan bosqichlarga ulushiga qarab taqsimlanadi. Payme/Click/Uzum chegirmali
  summani talab qiladi.
- Kod ariza formasida («🎁 Promo-kod bormi?»), buyurtma sahifasida (birinchi to'lovgacha) yoki
  havola orqali kiritiladi: `https://sayt.uz/?promo=KOD`.
- Statistika: «Platforma daromadi» chegirmalarni ayirib hisoblanadi.

**Mijoz referali.** Tasdiqlangan buyurtma sahifasida mijoz shaxsiy kod va havola oladi (Telegram'da
ulashish tugmasi bilan). Do'sti birinchi buyurtmasida `REFERRAL_DISCOUNT_PERCENT` (10%) chegirma oladi;
do'stning buyurtmasi **onlayn to'lanib tasdiqlansa**, kod egasiga keyingi buyurtma uchun bir martalik
mukofot kodi SMS'da keladi. O'z kodini ishlatib bo'lmaydi; mukofot kodi faqat egasining raqamiga.

**Usta referali.** Kabinetda shaxsiy havola (`/ustalar/royxatdan-otish/?ref=KOD`). Taklif qilingan usta
tekshiruvdan o'tib birinchi buyurtmasini bajarsa — taklif qilgan ustaga `MASTER_REFERRAL_TOP_DAYS`
(7) kun bepul TOP.

> Barcha foiz va summalar namunaviy — `.env` da o'zgartiring. Ofertada promo-kod bandi bor.

## Telefonda ilova (PWA) va bildirishnomalar

- Sayt telefonga ilova sifatida o'rnatiladi (`/manifest.webmanifest`, `/sw.js`): bosh ekranda ikonka,
  internet yo'qolsa — oflayn sahifa. Usta kabinetida «⬇ Ilovani o'rnatish» tugmasi.
- **Brauzer bildirishnomalari (Web Push):** usta kabinetda, mijoz buyurtma sahifasida (SMS kod bilan
  tasdiqlangan raqamda) «🔔 Bildirishnomalarni yoqish» ni bosadi. Buyurtma xabarlari (yangi buyurtma,
  holat, yozishma, kafolat) SMS/Telegram'ga **qo'shimcha** ravishda push bo'lib ham keladi.
- Sozlash: `python manage.py webpush_keys` → chiqqan ikki qatorni `.env` ga. Kalitsiz push o'chiq.
- Shifrlash RFC 8291/8292 bo'yicha faqat `cryptography` bilan yozilgan (`pywebpush` ning `http-ece`
  bog'liqligi ko'p serverlarda o'rnatilmaydi) va RFC dagi rasmiy test-namuna bilan tekshirilgan.
- iPhone: push faqat saytni «Ulashish → Bosh ekranga qo'shish» orqali o'rnatgandan keyin (iOS 16.4+).
- Xavfsizlik: obuna manzili faqat ma'lum push xizmatlariga (Google, Mozilla, Apple, Microsoft) ruxsat
  etiladi; eskirgan obunalar avtomatik o'chiriladi.

## Pul qaytarish

Nizo mijoz foydasiga hal qilinsa yoki admin «Mijozga qaytarish» amalini bossa, `/admin/` →
**Pul qaytarishlar** navbatida yozuv ochiladi (summa, to'lov tizimi, tranzaksiya raqami, nima qilish kerak):

- **Click** — `CLICK_AUTO_REFUND=True` bo'lsa, Click Merchant API orqali avtomatik
  (`DELETE /v2/merchant/payment/reversal/{service_id}/{payment_id}`). Click faqat joriy hisobot
  oyidagi to'lovlarni qaytaradi; rad etsa — yozuv «qo'lda» holatiga o'tadi. **Yoqishdan oldin
  Click bilan bitta kichik to'lovda sinab ko'ring.**
- **Payme** — Merchant API'da do'kon tomonidan qaytarish so'rovi yo'q: kassir Payme Business
  kabinetida tranzaksiyani bekor qiladi, Payme bizga `CancelTransaction` yuboradi va yozuv
  avtomatik «Qaytarildi» bo'ladi.
- **Uzum** — `reverse` so'rovi kelganda xuddi shunday.

Qaytarilganda mijoz xabar oladi. Qo'lda qaytarilganlarni «Qaytarildi deb belgilash» amali bilan yoping.

## Ustalarga haftalik to'lov

`process_orders` (cron) `PAYOUT_WEEKDAY` kuni (standart — dushanba) o'tkazmalarni tayyorlaydi:
kartasi bor, summasi `PAYOUT_MIN_AMOUNT` dan kam bo'lmagan va bosqichi chiqarilganiga
`PAYOUT_DELAY_HOURS` bo'lgan ustalar uchun. Administrator Telegram'da xabar oladi, Excel'ni
yuklab bank orqali o'tkazadi va «O'tkazmalar tarixi» da «O'tkazildi» deb belgilaydi — usta
SMS/Telegram/bildirishnoma oladi. «To'lanishi kerak» sahifasida «Hozir tayyorlash» tugmasi ham bor.
Usta kabinetida: keyingi to'lov sanasi, o'tkazilayotgan summa, karta.

**Avtomatik o'tkazma** (kartaga to'lash API'si) uchun to'lov tizimi bilan alohida shartnoma va
hujjat kerak — u ochiq emas, shuning uchun hozir faqat «qo'lda» usuli bor. Hujjat kelgach
`payments/payout_providers.py` ga bitta sinf (`send()`) qo'shiladi va `PAYOUT_PROVIDER` o'zgartiriladi;
jadval, xabarlar va hisobot o'zgarmaydi.

## Marketing xabarnomalari

`/admin/` → **Xabarnomalar**: matn (o'zbekcha/ruscha), havola, promo-kod, auditoriya va kanallar.
«Rejalashtirish» amalidan keyin cron partiyalab (`CAMPAIGN_BATCH`) va faqat `CAMPAIGN_HOURS`
(09–21) oralig'ida yuboradi.

- Mijozlarga — **faqat rozilik berganlarga**: ariza formasida va buyurtma sahifasida alohida,
  oldindan belgilanmagan belgi. Har xabarda obunani bekor qilish havolasi (`/obuna/bekor/<kalit>/`,
  bekor qilish tugma bilan — messenjer havolani oldindan ochganda tasodifan o'chib ketmasligi uchun).
- Auditoriya: barcha rozilik berganlar; uzoq vaqt buyurtma qilmaganlar; tanlangan yo'nalishda
  buyurtma qilganlar; ustalar (xizmat xabari).
- Har bir kishiga bitta xabar, eng arzon kanal orqali: bildirishnoma → Telegram → SMS (yoqilgan bo'lsa).
  SMS reklama matni Eskiz'da alohida tasdiqlanishi kerak.

## Tahlil: manbalar va voronka

Uchinchi tomon xizmatisiz, o'z bazamizda (`repair_service/analytics.py`):

- Birinchi tashrifda manba aniqlanadi — UTM (`?utm_source=instagram&utm_medium=cpc&utm_campaign=kuz`),
  qidiruv tizimi, Telegram, referal havola — va imzolangan cookie'ga yoziladi; ariza o'zi ham manbani saqlaydi.
- Hodisalar: ommaviy sahifa ochildi, ariza formasi to'ldirila boshlandi, ariza yuborildi.
  Tasodifiy tashrifchi ID; ism, telefon va IP saqlanmaydi; «Do Not Track»/GPC va botlar hisobga olinmaydi;
  `ANALYTICS_RETENTION_DAYS` (180) kundan keyin o'chiriladi.
- `/admin/statistika/`: «Saytdan arizagacha» voronkasi, manbalar bo'yicha tashriflar → ariza →
  bajarilgan → aylanma, eng ko'p ariza keltirgan kirish sahifalari.

## Ish vaqti va dam olish kunlari

Usta kabinetda «🕘 Ish vaqti» (`/kabinet/jadval/`) sahifasida ish kunlari, soatlari va dam olish/ta'til
kunlarini kiritadi.

- Dam olish kunida usta qidiruvda ko'rinmaydi, lentadan buyurtma olmaydi va yangi buyurtma xabari kelmaydi
  (mavjud buyurtmalari o'zgarmaydi).
- Ish vaqtidan tashqarida kartochka va profilda «🌙 Hozir ishlamaydi — ertaga 08:00 dan»; profilda jadval
  («Du–Ju 08:00–20:00»).
- Kelish vaqtini jadvaldan tashqariga qo'ysa — ogohlantirish (taqiq emas).
- Jadval kiritilmagan usta har doim ishlaydi deb hisoblanadi.

## «Yordam» — operator bilan yozishma

Har bir sahifada «💬 Yordam» vidjeti: tashrifchi (akkauntsiz) yoki usta operatorga yozadi; ixtiyoriy ism
va telefon. Operator `/admin/yordam/` da javob beradi (javob kutayotganlar yuqorida, mijozning buyurtmalari
bilan). Yangi suhbat haqida administrator chatiga Telegram keladi. Javob — vidjetda; ustaga Telegram yoki
bildirishnoma; telefon qoldirilgan bo'lsa — SMS havola (suhbatni istalgan qurilmada ochadi).

## Ustalar uchun o'quv bo'limi

`/kabinet/oqish/` — platforma qoidalari bo'yicha darslar: 6 ta boshlang'ich dars (bosqichlar, narx va eskrou,
kelish vaqti va muloqot, rasmlar, nizo/kafolat/ishonchlilik bali, pul olish va tariflar) migratsiya bilan
qo'shiladi. Admin → «O'quv darslari» da tahrirlanadi va yangisi qo'shiladi (YouTube video bilan).
Matndagi raqamlar sozlamalardan olinadi (`{komissiya}`, `{kafolat_kun}`, `{tolov_kuni}` …) — siz
komissiyani o'zgartirsangiz, darslar ham o'zgaradi. Usta kabinetida «Boshlang'ich kurs: 2/6» eslatmasi.

## A/B testlar

Admin → «A/B testlar»: kalit, variantlar (`a,b`), «Faol». Shablonda:

```django
{% load ui %}{% ab 'ariza_tugmasi' as v %}
{% if v == 'b' %}Usta chaqirish — bepul{% else %}Ariza yuborish{% endif %}
```

Har tashrifchi doim bitta variantni ko'radi. Natija (admin'da): har variant bo'yicha tashrifchilar, forma
boshlaganlar, ariza yuborganlar, nazorat variantiga nisbatan farq va p-qiymat. Har variantda kamida 100
tashrifchi va p < 0.05 bo'lsa — «ahamiyatli». G'olibni «G'olib» maydoniga yozsangiz, hamma shu variantni
ko'radi. Tayyor namuna: ariza formasi tugmasi (`ariza_tugmasi`) — testni yaratib, faollashtirish kifoya.

## Yuridik shaxslar (tashkilot, ofis, do'kon)

- Arizada «🏢 Tashkilot nomidan»: nomi, STIR (9 raqam), yuridik manzil.
- Onlayn to'lov rejasida har bir bosqichda **«Bank o'tkazmasi (schyot)»** — chop etiladigan to'lov uchun
  schyot: platforma rekvizitlari, buyurtmachi, summa (QQS bilan yoki «QQSsiz»), to'lov maqsadi
  («Schyot № TS-<buyurtma>-<bosqich>»). Havolani tashkilot buxgalteriyasiga yuborish mumkin.
- Pul hisobga tushgach admin → «Bank o'tkazmalari (schyot)» → «Bank o'tkazmasi tushdi» — bosqich to'langan
  bo'ladi, usta ishni davom ettiradi (karta to'lovi bilan bir xil eskrou qoidalari).
- Buyurtma tasdiqlangach — **bajarilgan ishlar dalolatnomasi** (chop etish/PDF).
- `.env`: `SITE_LEGAL_NAME`, `SITE_LEGAL_INN`, `SITE_BANK_NAME`, `SITE_BANK_ACCOUNT`, `SITE_BANK_MFO`,
  `SITE_VAT_PERCENT` (bo'sh — QQSsiz). Rekvizitlar to'ldirilmaguncha bank o'tkazmasi taklif qilinmaydi.

> ⚠️ Schyot va dalolatnoma — buxgalteriya hujjatlari. **Elektron hisob-faktura (ESF)** soliq tizimi
> operatori (Didox, Faktura.uz va h.k.) orqali buxgalter tomonidan alohida rasmiylashtiriladi. Platforma
> qaysi rolda (agent yoki ijrochi) ekanini, QQS va hujjat shakllarini buxgalter va yurist bilan aniqlang.

## Ustalarni jalb qilish

- `/ustalar-uchun/` — ustalar uchun sahifa: afzalliklar, so'nggi 30 kundagi talab (yo'nalishlar bo'yicha),
  qanday boshlash, savollar. Saytdagi «Usta bo'lish» shu yerga olib boradi. Reklama uchun UTM bilan:
  `/ustalar-uchun/?utm_source=olx&utm_campaign=start` — statistikada «Yangi ustalar manbasi».
- **Birinchi oy bepul TOP:** usta birinchi marta tasdiqlanganda `NEW_MASTER_FREE_TOP_DAYS` (30) kun TOP
  (bir marta, SMS/Telegram xabari bilan). Mavjud ustalarga orqaga sanab berilmaydi.
- Kabinetda **«Ishni boshlashga tayyorlik»** — 7 band: rasm, o'zi haqida, hujjatlar, karta, Telegram yoki
  bildirishnoma, ish vaqti, boshlang'ich kurs.
- Taklif havolalari (usta referali) avvalgidek: taklif qilingan usta birinchi ishini bajarsa — bepul TOP.

## Mijozlar fikri (NPS)

«Bizni do'stingizga tavsiya qilasizmi?» (0–10) va ixtiyoriy izoh — tasdiqlangan buyurtma sahifasida va
bahodan keyin; bir buyurtmaga bir marta. Tasdiqlangandan `NPS_INVITE_HOURS` (24) soat keyin eslatma —
faqat Telegram yoki bildirishnoma orqali (SMS'siz). 0–6 bergan (norozi) mijoz haqida administratorga
darhol Telegram — qo'ng'iroq qilib, muammoni hal qiling va admin'da «bog'lanildi» deb belgilang.
Statistikada: NPS (−100…+100), taqsimot va norozilar ro'yxati.

## Ishga tushirish

**Qadamma-qadam:** [docs/ISHGA_TUSHIRISH.md](docs/ISHGA_TUSHIRISH.md) — yuridik asos, shartnomalar
(Eskiz, Payme, Click), domen, server, kontent, tekshiruv va birinchi haftalar.

```bash
docker compose up -d --build                       # sayt + PostgreSQL + Redis + cron + HTTPS (Caddy)
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py launch_check --live   # nima qolganini ko'rsatadi
```

`launch_check` — xavfsizlik (`check --deploy`), integratsiyalar va kontent: namunaviy kontaktlar, yuridik
ma'lumotlar, demo ustalar qolib ketmaganmi, administrator, yo'nalishlar va narxlar, ustalar soni.

## Telegram bot

Bitta bot ikki vazifani bajaradi (admin'ga yangi ariza xabari ham shu bot orqali):

- **Buyurtmachi** buyurtma sahifasida «Telegram'da kuzatish» ni bosadi — bot buyurtmaga
  ulanadi va holat o'zgarishlari **SMS o'rniga Telegram'ga** keladi (SMS pulini tejaydi).
- **Usta** kabinetda «Telegram'ni ulash» ni bosadi (bir martalik kod, 30 daqiqa).
  Yangi buyurtmalar Telegram'ga **tugmalar bilan** keladi: «Qabul qilish» → «Joyga yetib
  keldim» → … — saytga kirmasdan boshqaradi. Barcha qoidalar (navbat, narx, to'lov)
  botda ham amal qiladi; tugma faqat shu buyurtma ustasining chatidan ishlaydi.
- **Ochiq buyurtmalar** yaqin atrofdagi ustalarga «✋ Olish» tugmasi bilan keladi.
- **Rasm yuborish**: usta yoki mijoz botga rasm yuborsa, u faol buyurtmaga biriktiriladi
  (ustada bir nechta faol buyurtma bo'lsa, bot qaysi biri ekanini so'raydi).
- Buyruqlar: `/buyurtmalar`, `/stop` (uzish — xabarlar yana SMS'ga qaytadi).

Sozlash: @BotFather'da bot yarating, `.env` ga `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`,
`TELEGRAM_WEBHOOK_SECRET` yozing, saytni HTTPS'da ishga tushirib bir marta:

```bash
python manage.py telegram_webhook
```

## Tillar

O'zbekcha (standart, `/ustalar/`) va ruscha (`/ru/ustalar/`). Sarlavhadagi UZ/RU
tugmasi bilan almashtiriladi; qidiruv tizimlari uchun `hreflang` qo'yilgan.
Kategoriya va narx nomlarining ruscha varianti admin'da `… (ruscha)` maydonlarida.
Mijozga SMS buyurtma qaysi tilda berilgan bo'lsa, o'sha tilda yuboriladi.

Matnlarni o'zgartirgach:

```bash
python manage.py makemessages -l ru   # GNU gettext kerak
# locale/ru/LC_MESSAGES/django.po ni tahrirlang
python manage.py compilemessages -l ru
```

Kompilyatsiya qilingan `django.mo` repozitoriyda bor — Windows'da gettext o'rnatish shart emas.

## Ishonch va xavfsizlik qarorlari

| Muammo | Yechim |
|---|---|
| Soxta baholar | Baho faqat **bajarilgan ariza** uchun berilgan maxsus havola orqali, har buyurtmaga bitta |
| 1 ta 5★ bahosi bor usta 200 ta 4.8★ li ustadan yuqori chiqishi | Reyting bo'yicha saralashda **Bayes o'rtachasi** |
| Ustaning uy manzili oshkor bo'lishi | Xarita va API'da koordinata ~1 km aniqlikkacha yaxlitlanadi |
| Tekshirilmagan odamlar usta bo'lib chiqishi | Admin tasdiqlamaguncha usta qidiruvda ko'rinmaydi |
| Usta o'zi bormaydigan uzoqlikdagi mijozga ko'rinishi | Har ustaning o'z xizmat radiusi hisobga olinadi |
| Spam arizalar | Bot tuzog'i (honeypot) + bitta IP'dan 10 daqiqada 5 ta ariza |
| Shaxsga doir ma'lumotlar | Har bir formada rozilik belgisi, rozilik bazada saqlanadi |

## O'rnatish

Python 3.10+ kerak.

```bash
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux/Mac

pip install -r requirements.txt
copy .env.example .env           # Linux/Mac: cp .env.example .env  — keyin qiymatlarni to'ldiring
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo       # kategoriyalar, narxlar, brendlar
python manage.py runserver
```

- Sayt: http://127.0.0.1:8000/
- Ustalar: http://127.0.0.1:8000/ustalar/
- Admin: http://127.0.0.1:8000/admin/

**Namoyish uchun demo ustalar:** `python manage.py seed_demo --masters` — 10 ta usta
(Toshkent tumanlari bo'ylab), bajarilgan arizalar va baholar qo'shadi. Kirish: telefon
`+998 99 100-00-00` … `-09`, parol `demo-parol-123`. **Haqiqiy saytda ishlatmang** —
uydirma ustalar va baholar mijozlarni chalg'itadi.

### Eski versiyadan yangilash

`git pull` dan keyin `pip install -r requirements.txt` va `python manage.py migrate`
yetarli. Mavjud arizalar saqlanadi — har biriga alohida baho kaliti beriladi.

## Sahifalar

| URL | Vazifasi |
|---|---|
| `/` | Bosh sahifa: qidiruv, yo'nalishlar, top ustalar, narxlar, ariza |
| `/ustalar/?category=santexnik&district=chilonzor&radius=10&sort=rating` | Qidiruv |
| `/ustalar/<id>/` | Usta profili va ariza |
| `/ustalar/royxatdan-otish/` | Usta ro'yxatdan o'tishi |
| `/kirish/`, `/kabinet/` | Usta kabineti |
| `/kabinet/ochiq/` | Ochiq buyurtmalar lentasi |
| `/kabinet/tarif/` | Tariflar (TOP, PRO) |
| `/buyurtma/<kalit>/` | Mijozning buyurtma sahifasi (kuzatish, to'lov, yozishma, kafolat) |
| `/oferta/`, `/maxfiylik/` | Ommaviy oferta va maxfiylik siyosati |
| `/admin/statistika/` | Statistika (faqat administrator) |
| `/admin/nizolar/` | Nizolar: dalillar va qaror (faqat administrator) |
| `/obuna/bekor/<kalit>/` | Aksiya xabarlaridan voz kechish |
| `/kabinet/jadval/`, `/kabinet/oqish/` | Usta: ish vaqti, o'quv bo'limi |
| `/ustalar-uchun/` | Ustalar uchun sahifa (jalb qilish) |
| `/buyurtma/<kalit>/schyot/<bosqich>/`, `/buyurtma/<kalit>/dalolatnoma/` | Tashkilotlar: schyot va dalolatnoma |
| `/admin/yordam/` | Operator: «Yordam» suhbatlari |
| `/manifest.webmanifest`, `/sw.js`, `/offline/` | Telefonda ilova (PWA) |
| `/ustalar/<yo'nalish>/`, `/ustalar/<yo'nalish>/<tuman>/` | SEO sahifalari |
| `/kabinet/hujjatlar/` | Usta: shaxsni tasdiqlash |
| `/buyurtma/<kalit>/qayta/` | Mijoz: ustani qayta chaqirish |
| `/sitemap.xml`, `/robots.txt`, `/healthz/` | Qidiruv tizimlari va monitoring uchun |
| `/baho/<kalit>/` | Mijoz bahosi |
| `/api/ustalar/?lat=41.31&lng=69.28&category=elektrik` | JSON API (mobil ilova uchun) |

## Loyiha tuzilmasi

```
config/              sozlamalar, URL'lar, admin dashboard (dashboard.py)
repair_service/      arizalar, narxlar, brendlar, bosh sahifa, Telegram xabari
  phone.py             +998 raqamlarni yagona formatga keltirish
masters/             ustalar, kategoriyalar, baholar, qidiruv
  geo.py               masofa (haversine) — PostGIS'siz
  services.py          qidiruv va saralash
  locations.py         Toshkent tumanlari koordinatalari
templates/           base.html, bosh sahifa, masters/*, admin/index.html
static/css/app.css   dizayn tizimi (framework'siz, tungi rejim bilan)
static/js/app.js     telefon maskasi, geolokatsiya, AJAX formalar, xarita (jQuery'siz)
Dockerfile, docker-compose.yml   bitta buyruq bilan o'rnatish (HTTPS — deploy/Caddyfile)
deploy/              serverga o'rnatish: gunicorn, systemd, nginx, cron, deploy.sh, backup.sh
docs/                integratsiyalarni haqiqiy muhitda sinash tartibi
e2e/                 brauzerda to'liq ssenariy (Playwright)
.github/workflows/   testlar har push'da SQLite va PostgreSQL+Redis'da, brauzer ssenariysi
```

## Testlar

```bash
python manage.py test
```

324 ta test: telefon formati, masofa va qidiruv, ro'yxatdan o'tish, buyurtma
bosqichlari (navbat, bekor qilish qoidalari, avtomatik tasdiqlash), eskrou
(rejalar, bosqichlar, nizo, avtomatik chiqarish), Payme protokoli, SMS kod
(muddat, urinishlar, cheklovlar, Eskiz), rus tili, admin sahifalari, Click va Uzum protokollari, Telegram bot (ulash, tugmalar, rasm, xavfsizlik), tariflar,
ochiq buyurtmalar lentasi, kafolat, kelish vaqti, yozishma, o'tkazmalar hisoboti (Excel), statistika,
yuridik sahifalar, production tekshiruvlari, `check_integrations`, ustalar hujjatlari (maxfiylik, huquqlar),
qayta chaqirish, SEO (sitemap, robots, canonical, JSON-LD), viloyatlar, PWA va Web Push (RFC 8291 test-namunasi),
nizolar sahifasi, ishonchlilik bali, promo-kodlar va referal (Payme chegirmali summani talab qilishi bilan),
tahlil (manba, DNT, botlar), marketing (rozilik, tinch soatlar, partiyalar), pul qaytarish (Payme bekor qilishi,
Click API imzosi), haftalik to'lov jadvali, ish vaqti, «Yordam» chati, o'quv bo'limi, A/B testlar,
ustalarni jalb qilish (bepul TOP, tayyorlik), NPS, yuridik shaxslar (schyot, bank o'tkazmasi, dalolatnoma), launch_check.

**Brauzerda to'liq ssenariy** (11 qadam: ariza → to'lov → baho → ustaga to'lov → kafolat → qayta chaqirish):

```bash
bash e2e/run.sh        # alohida sinov bazasi; talab: npm i -g playwright@1.63.0 && npx playwright install chromium
```

Production'dagidek PostgreSQL va Redis bilan:

```bash
DATABASE_URL=postgres://user:parol@127.0.0.1:5432/techservice REDIS_URL=redis://127.0.0.1:6379/1 \
    python manage.py test --parallel 1
```

## Production

To'liq qo'llanma: **[deploy/README.md](deploy/README.md)** — Ubuntu VPS, PostgreSQL, Redis,
gunicorn (systemd), nginx + HTTPS (certbot), cron, kunlik zaxira va tiklash, yangilash skripti.

Qisqacha:

- `requirements-prod.txt` — gunicorn, psycopg, redis.
- `.env`: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` (standart kalit bilan sayt ishga tushmaydi),
  `DATABASE_URL`, `REDIS_URL`, `SITE_URL=https://...`, `DJANGO_MEDIA_ROOT`, `DJANGO_PRIVATE_MEDIA_ROOT`.
- `python manage.py check --deploy` — Django xavfsizlik tekshiruvlari + loyiha tekshiruvlari
  (`techservice.W001…W008`: kesh, baza, SMS, SITE_URL, to'lov tizimlari, demo to'lov, oferta,
  maxfiy papka). Hammasi tuzatilgach «no issues».
- `python manage.py check_integrations [--live]` — Payme/Click/Uzum kalitlari, Eskiz, Telegram
  webhook va sayt manzilini tekshiradi; haqiqiy sinov tartibi — [docs/INTEGRATSIYALAR.md](docs/INTEGRATSIYALAR.md).
- `/healthz/` — tashqi monitoring uchun (baza va kesh). `127.0.0.1` va `localhost` har doim ruxsat
  etilgan — server ichidagi tekshiruv (Docker HEALTHCHECK, `deploy.sh`) `DisallowedHost` bermaydi.
- `DJANGO_DEBUG` ko'rsatilmasa: `DJANGO_SECRET_KEY` berilgan bo'lsa — `False`, berilmagan bo'lsa
  (dasturchi kompyuteri) — `True`.
- Admin xodimlari: «Nizolar», «Yordam», «Statistika» va «To'lanishi kerak» sahifalari uchun
  `is_staff` yetarli emas — mos model huquqi kerak (ko'rish: `view_*`, amal: `change_*`;
  statistika — `payments.view_payment`). Tayyor rollar: `python manage.py setup_roles`
  (deploy'da avtomatik) — **Operator** (yordam, arizalar, ustalarni tekshirish), **Nizo hakami**,
  **Moliyachi** (o'tkazmalar, qaytarishlar, bank), **Marketolog** (aksiyalar, promo, A/B).
  Xodimga: Admin → Foydalanuvchilar → «Xodim» + guruh.
- Monitoring: `SENTRY_DSN` (ixtiyoriy, shaxsiy ma'lumotsiz), UptimeRobot → `/healthz/`, cron xatosi
  Telegram'ga — batafsil [deploy/README.md](deploy/README.md#monitoring).
- Payme sandbox: `python manage.py payme_sandbox` — sinov bosqichi va sandbox formasi qiymatlari.
- Ushlab turilgan pulni chiqarish/qaytarish faqat «Nizolar» sahifasi orqali; platformada pul
  bo'lmasa (naqd reja) qaror kimning foydasiga ekanini tanlaysiz.
- Mijoz Telegram botni faqat SMS-kod bilan tasdiqlangan brauzerdan ulay oladi (30 daqiqalik
  imzolangan havola) — buyurtma havolasining o'zi yetmaydi.
- **HTTPS majburiy** — brauzerlar geolokatsiyani faqat HTTPS (yoki localhost) da beradi.
- Shaxsga doir ma'lumotlar: 2026-yil 27-martdan kuchga kirgan o'zgartirishlarga
  ko'ra O'zbekistonda saqlash majburiyati asosan biometrik va genetik ma'lumotlarga
  qoldirilgan; boshqalarini chet elda saqlash shartlar bilan ruxsat etilgan.
  Hosting tanlashdan oldin amaldagi tahririni lex.uz da va yurist bilan tekshiring.
