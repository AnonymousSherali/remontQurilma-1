/* To'liq ssenariy — haqiqiy brauzerda. Har qadam tekshiriladi; xato bo'lsa skrinshot e2e/artifacts/ ga. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.E2E_BASE;
const CREDS = JSON.parse(process.env.E2E_CREDS);
const ART = path.join(__dirname, 'artifacts');
const PHONE = '+998901234321';
let step = 0;

function assert(cond, msg) { if (!cond) { throw new Error(msg); } }

async function run(name, fn) {
  step += 1;
  process.stdout.write(`${String(step).padStart(2)}. ${name} … `);
  await fn();
  console.log('✓');
}

(async () => {
  fs.mkdirSync(ART, { recursive: true });
  const browser = await chromium.launch();
  const errors = [];
  async function page(width) {
    const ctx = await browser.newContext({ viewport: { width: width || 1280, height: 900 } });
    const p = await ctx.newPage();
    p.on('pageerror', (e) => errors.push(e.message));
    p.on('dialog', (d) => d.accept());
    return p;
  }
  const customer = await page(390);   // mijoz — telefonda
  const master = await page();
  const admin = await page();
  let trackUrl = '';
  try {
    await run('Mijoz ariza qoldiradi (tuman bilan)', async () => {
      await customer.goto(BASE + '/');
      await customer.fill('#main-name', 'Dilnoza');
      await customer.fill('#main-phone', PHONE);
      const cat = await customer.$eval('#main-category', (el) => [...el.options].find((o) => o.text.includes('Santexnik')).value);
      await customer.selectOption('#main-category', cat);
      await customer.selectOption('#main-district', 'chilonzor');
      await customer.fill('#main-problem', 'Oshxonada kran oqyapti');
      await customer.check('form.js-request-form input[name=consent]');
      await customer.click('form.js-request-form button[type=submit]');
      const track = customer.locator('.form-success [data-track]').first();
      await track.waitFor({ state: 'visible' });
      trackUrl = BASE + (await track.getAttribute('href'));
      assert(trackUrl.includes('/buyurtma/'), 'kuzatish havolasi yo\'q');
    });

    await run('Usta kiradi va lentadan buyurtmani oladi', async () => {
      await master.goto(BASE + '/kirish/');
      await master.fill('input[name=username]', CREDS.master_phone);
      await master.fill('input[name=password]', CREDS.master_password);
      await Promise.all([master.waitForNavigation(), master.click('form button[type=submit]')]);
      await master.goto(BASE + '/kabinet/ochiq/');
      assert(!(await master.content()).includes('Dilnoza'), 'lentada mijoz ismi ko\'rinmasligi kerak');
      await Promise.all([master.waitForNavigation(), master.click('text=Olish')]);
      assert((await master.content()).includes('Dilnoza'), 'olgandan keyin mijoz ismi ochilishi kerak');
    });

    await run('Usta kelish vaqtini belgilaydi va narx taklif qiladi', async () => {
      await master.fill('input[name=time]', '18:30');
      await Promise.all([master.waitForNavigation(), master.click('text=Vaqtni belgilash')]);
      await master.fill('input[name=amount]', '200000');
      await master.check('input[name=plan][value=on_completion]');
      await Promise.all([master.waitForNavigation(), master.click('text=Narxni mijozga yuborish')]);
    });

    await run('Mijoz SMS kod bilan kiradi, narxga rozi bo\'ladi va to\'laydi', async () => {
      await customer.goto(trackUrl);
      await customer.click('[data-otp-send]');
      const debug = customer.locator('[data-otp-debug]');
      await debug.waitFor({ state: 'visible' });
      const code = (await debug.textContent()).match(/\d{6}/)[0];
      await Promise.all([customer.waitForNavigation(), customer.fill('[data-otp-code]', code)]);
      await Promise.all([customer.waitForNavigation(), customer.click('text=Narxga roziman')]);
      await Promise.all([customer.waitForNavigation(), customer.click('button[name=provider]')]);
      await Promise.all([customer.waitForNavigation(), customer.click('form button:has-text("To\'lash")')]);
      assert((await customer.content()).includes('Ushlab turilibdi'), 'to\'lov ushlab turilgan bo\'lishi kerak');
    });

    await run('Usta: joyida → ishda → bajarildi', async () => {
      for (let i = 0; i < 3; i++) {
        await master.reload();
        await Promise.all([master.waitForNavigation(), master.click('.results-bar form button')]);
      }
      assert((await master.content()).includes('Bajarildi'), 'holat «Bajarildi» bo\'lishi kerak');
    });

    await run('Yozishma: mijoz yozadi, usta ko\'radi', async () => {
      await customer.goto(trackUrl);
      await customer.fill('#chat-text', 'Rahmat, ish yaxshi chiqdi');
      await customer.press('#chat-text', 'Enter');
      await customer.locator('.chat__msg--mine').first().waitFor();
      await master.reload();
      assert((await master.content()).includes('Rahmat, ish yaxshi chiqdi'), 'usta xabarni ko\'rmadi');
    });

    await run('Mijoz tasdiqlaydi va 5 yulduz bilan baholaydi', async () => {
      await customer.goto(trackUrl);
      await Promise.all([customer.waitForNavigation(), customer.click('text=Natijani tasdiqlash')]);
      for (const name of ['quality', 'punctuality', 'price', 'politeness']) {
        await customer.click(`label[for=id_${name}_5]`);   // foydalanuvchi kabi — yulduzni bosish
      }
      await Promise.all([customer.waitForNavigation(), customer.click('form button[type=submit]')]);
      await customer.goto(trackUrl);
      assert((await customer.content()).includes('Tasdiqlandi'), 'buyurtma tasdiqlanmadi');
    });

    await run('Admin ustaga pulni o\'tkazildi deb belgilaydi', async () => {
      await admin.goto(BASE + '/admin/login/');
      await admin.fill('input[name=username]', CREDS.admin);
      await admin.fill('input[name=password]', CREDS.admin_password);
      await Promise.all([admin.waitForNavigation(), admin.click('form button[type=submit], form input[type=submit]')]);
      await admin.goto(BASE + '/admin/payments/payout/pending/');
      await admin.check('input[name=master]');
      await Promise.all([admin.waitForNavigation(), admin.click('text=O\'tkazildi deb belgilash')]);
      await admin.goto(BASE + '/admin/payments/payout/');
      assert((await admin.content()).includes('180 000'), 'ustaga 180 000 so\'m (komissiyasiz) o\'tkazilishi kerak');
    });

    await run('Kafolat: mijoz murojaat qiladi, usta tuzatadi, mijoz yopadi', async () => {
      await customer.goto(trackUrl);
      await customer.click('#kafolat summary');
      await customer.fill('#wdesc', 'Kran yana tomchilayapti');
      await Promise.all([customer.waitForNavigation(), customer.click('text=Murojaat yuborish')]);
      await master.reload();
      await Promise.all([master.waitForNavigation(), master.click('text=Tuzatdim')]);
      await customer.goto(trackUrl);
      await Promise.all([customer.waitForNavigation(), customer.click('text=Muammo hal bo\'ldi')]);
      assert((await customer.content()).includes('Hal bo\'ldi'), 'kafolat murojaati yopilmadi');
    });

    await run('Yordam vidjeti: savol operatorga yetadi', async () => {
      await customer.goto(BASE + '/');
      await customer.click('[data-support-toggle]');
      await customer.fill('#support-panel textarea', 'Elektrik ham bormi?');
      await customer.press('#support-panel textarea', 'Enter');
      await customer.locator('#support-panel .chat__msg--mine').first().waitFor();
      await admin.goto(BASE + '/admin/yordam/');
      assert((await admin.content()).includes('Elektrik ham bormi?'), 'operator savolni ko\'rmadi');
    });

    await run('Mijoz ustani qayta chaqiradi', async () => {
      await customer.goto(trackUrl);
      await Promise.all([customer.waitForNavigation(), customer.click('text=Shu ustani qayta chaqirish')]);
      await customer.fill('#r-problem', 'Hammomdagi kran ham');
      await customer.check('input[name=consent]');
      await Promise.all([customer.waitForNavigation(), customer.click('text=Ustaga yuborish')]);
      assert(customer.url().includes('/buyurtma/') && customer.url() !== trackUrl, 'yangi buyurtma ochilmadi');
    });

    assert(errors.length === 0, 'brauzerda JS xatolari: ' + errors.join('; '));
    console.log(`\nHammasi o'tdi: ${step} ta qadam.`);
  } catch (error) {
    console.log('✗\n' + error.message);
    for (const [name, p] of [['mijoz', customer], ['usta', master], ['admin', admin]]) {
      await p.screenshot({ path: path.join(ART, `xato-${name}.png`), fullPage: true }).catch(() => {});
    }
    console.log(`Skrinshotlar: ${ART}`);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
