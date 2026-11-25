# Integratsiyalarni haqiqiy muhitda sinash

Kod protokol testlari bilan qoplangan (`python manage.py test`), lekin to'lov tizimi va SMS
shlyuzining **o'z tomoni** — kabinetdagi sozlamalar, sinov muhiti, shablon moderatsiyasi —
faqat ular bilan bog'lanib tekshiriladi. Quyidagi tartib shu uchun.

Avval har doim:

```bash
python manage.py check_integrations          # sozlamalar + saytning o'z endpointlari
python manage.py check_integrations --live   # + Eskiz, Telegram, SITE_URL/healthz/
```

`check_integrations` .env dagi kalit bilan imzolangan so'rovni saytning o'z endpointiga yuboradi
(mavjud bo'lmagan hisob raqami bilan — hech narsa yaratilmaydi). «✓» — kalit va endpoint mos;
to'lov tizimi kabinetiga ham aynan shu kalitni kiritsangiz, u ham ulana oladi.

Sinov uchun alohida server (masalan `test.techservice.uz`) va alohida ma'lumotlar bazasi
ishlatgan ma'qul: sinov to'lovlari haqiqiy hisobotlarga aralashmaydi.

## 1. Eskiz (SMS)

1. my.eskiz.uz da ro'yxatdan o'ting, shartnoma tuzing, jo'natuvchi nomi (`SMS_SENDER`) oling.
2. **Shablonlar.** Eskiz har bir SMS matnini oldindan tasdiqlaydi; tasdiqlanmagan matn
   yuborilmaydi. Yangi akkaunt sinov rejimida faqat Eskiz bergan sinov matnini yubora oladi.
   Tasdiqlash uchun yuboriladigan matnlar (o'zbek va rus tilida — `locale/ru/.../django.po`):
   - `otp/services.py` — tasdiqlash kodi;
   - `repair_service/customer_notify.py` — buyurtma holati, narx taklifi, usta xabarlari;
   - `repair_service/schedule.py` — kelish vaqti va eslatma;
   - `repair_service/chat.py`, `repair_service/warranty.py` — yozishma va kafolat xabarlari.
3. `.env`: `SMS_BACKEND=eskiz`, `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `SMS_SENDER`.
4. `check_integrations --live` → «Eskiz: kirish muvaffaqiyatli».
5. Saytda «Mening buyurtmalarim» → o'z raqamingizga kod so'rang. Kod kelmasa: Eskiz kabinetidagi
   SMS tarixida xabar holati (rad etilgan bo'lsa — shablon mos emas).

## 2. Payme (Merchant API)

1. Payme Business'da kassa oching; **sinov kaliti** (test key) va kassa ID sini oling.
2. Kassa sozlamalarida endpoint: `https://<domen>/payments/payme/`, hisob maydoni: `milestone_id`
   (`PAYME_ACCOUNT_KEY`). Tarif xaridlari uchun hisob qiymati `p<raqam>` ko'rinishida keladi.
3. `.env`: `PAYMENT_PROVIDERS=payme`, `PAYME_MERCHANT_ID`, `PAYME_KEY=<sinov kaliti>`, `PAYME_TEST=True`.
4. **Sandbox** (test.paycom.uz): kassa ID, endpoint va sinov kalitini kiritib, barcha
   ssenariylarni ishga tushiring — noto'g'ri avtorizatsiya, noto'g'ri summa, mavjud bo'lmagan hisob,
   yaratish → bajarish → bekor qilish, takroriy so'rovlar. Hammasi yashil bo'lishi kerak.
   Sandbox uchun avval saytda buyurtma yarating va narxni onlayn to'lov rejasida tasdiqlang —
   sandbox'ga shu bosqichning raqami va summasi (tiyinda: so'm × 100) kerak.
5. Haqiqiy kalitga o'tish: `PAYME_KEY=<haqiqiy kalit>`, `PAYME_TEST=False`; kichik summali
   haqiqiy to'lov qilib, admin → «To'lov bosqichlari» da holat «Ushlab turilibdi» bo'lganini va
   Payme kabinetidagi tranzaksiya bilan mosligini tekshiring.

## 3. Click (Shop API)

1. Click bilan shartnoma → merchant kabinetida servis yarating, `service_id`, `merchant_id`,
   `secret_key`, `merchant_user_id` ni oling.
2. Servis sozlamalarida Prepare URL: `https://<domen>/payments/click/prepare/`,
   Complete URL: `https://<domen>/payments/click/complete/`.
3. `.env`: `PAYMENT_PROVIDERS=payme,click`, `CLICK_*` to'rt qiymat.
4. `check_integrations` → «Click ✓» (imzo `CLICK_SECRET_KEY` bilan mos).
5. Click texnik yordamidan servisni sinov rejimida tekshirishni so'rang yoki kichik summali
   haqiqiy to'lov qiling: buyurtma sahifasida «Click» → to'lov → bosqich holati «Ushlab turilibdi».
   Bekor qilish ssenariysi: to'lov sahifasida to'lamay chiqing — tranzaksiya admin'da bekor bo'ladi.

## 4. Uzum Bank

⚠️ `payments/uzum.py` Uzum rasmiy hujjatiga qaramasdan yozilgan (hujjat faqat hamkorlarga
beriladi). Uzum bilan shartnomadan keyin olingan hujjat bilan quyidagilarni solishtiring va
farq bo'lsa kodni to'g'rilang: endpoint nomlari (`check`, `create`, `confirm`, `reverse`,
`status`), so'rov va javob maydonlari, xato kodlari (`10001`…`10017`), avtorizatsiya, to'lov
sahifasi havolasi. Shundan keyingina `PAYMENT_PROVIDERS` ga `uzum` qo'shing.

## 5. Telegram bot

1. @BotFather → yangi bot → token. `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`
   (@ belgisisiz), `TELEGRAM_WEBHOOK_SECRET` (tasodifiy uzun satr), `TELEGRAM_CHAT_ID`
   (administrator chati — yangi ariza xabarlari uchun).
2. Sayt HTTPS'da ishlab turganda: `python manage.py telegram_webhook`.
3. `check_integrations --live` → «webhook ulangan».
4. Sinov: usta kabinetida «Telegram'ni ulash» → botda /start → yangi buyurtma xabari tugmalar bilan
   keladi; botga rasm yuboring → buyurtmaga biriktiriladi.

## 6. To'liq ssenariy

**Avtomatik (har o'zgarishda):** `bash e2e/run.sh` — alohida sinov bazasida, demo to'lov va konsol SMS bilan,
haqiqiy brauzerda 11 qadam: ariza → usta lentadan oladi → kelish vaqti va narx → mijoz SMS kod bilan kiradi,
rozi bo'ladi va to'laydi → bosqichlar → yozishma → tasdiqlash va baho → admin ustaga to'lovni belgilaydi →
kafolat → «Yordam» vidjeti → qayta chaqirish. GitHub Actions'da ham ishlaydi (`e2e` job).
Talab: `npm i -g playwright@1.63.0 && npx playwright install chromium`.

Bu test **sizning kodingiz** to'g'ri ishlashini tekshiradi; to'lov tizimi va SMS shlyuzining o'z tomonini
emas. Shuning uchun ishga tushirishdan oldin pastdagi ssenariylarni **haqiqiy telefonlarda, Payme sandbox
va Eskiz bilan** bir marta qo'lda o'tkazing:

| # | Ssenariy | Kutilgan natija |
|---|---|---|
| 1 | Usta ro'yxatdan o'tadi (SMS kod), hujjat yuklaydi | Admin'da «Tekshiruvda», tasdiqlangach qidiruvda ko'rinadi |
| 2 | Mijoz ustasiz ariza qoldiradi (tuman bilan) | Mijozga SMS; yaqin ustalarga Telegram'da «✋ Olish» |
| 3 | Usta oladi, kelish vaqtini belgilaydi | Mijozga xabar; 2 soat oldin ikkalasiga eslatma |
| 4 | Usta narx taklif qiladi (3 qism), mijoz SMS kod bilan tasdiqlaydi | Bosqichlar paydo bo'ladi |
| 5 | Mijoz 1-qismni Payme sinov kartasi bilan to'laydi | Bosqich «Ushlab turilibdi», usta ishni boshlay oladi |
| 6 | Usta «Bajarildi», mijoz tasdiqlaydi va baholaydi | Mablag' ustaga chiqariladi, baho profilda |
| 7 | Admin → «Ustalarga to'lanishi kerak» → Excel → «O'tkazildi» | O'tkazma tarixida yozuv |
| 8 | Mijoz kafolat murojaati ochadi | Ustaga xabar, «Tuzatdim» → mijoz tasdiqlaydi |
| 9 | Mijoz nizo ochadi | To'lov muzlaydi, admin hal qiladi |
| 10 | Mijoz ustani qayta chaqiradi | Yangi buyurtma o'sha ustaga |
