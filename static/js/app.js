/**
 * TechService — sayt skriptlari (jQuery'siz).
 *
 *  - mobil menyu
 *  - telefon maskasi:          <input data-phone>
 *  - joylashuvni aniqlash:     <button data-geolocate>
 *  - AJAX ariza formalari:     <form class="js-request-form">
 *  - Yandex xarita:            <div data-map="points-json-id">, tanlash rejimi: data-map-picker
 *  - nusxa olish:              <button data-copy="#input">
 *  - yozishma:                 <div data-chat data-url="...">
 */
(function () {
  'use strict';

  // Tarjima qilingan matnlar base.html dagi <script id="js-i18n"> dan
  var T = Object.assign({
    resend: 'Qayta yuborish', debugCode: 'Sinov rejimi, kod:', network: "Tarmoq xatosi. Qaytadan urinib ko'ring.",
    fixErrors: "Formadagi xatolarni to'g'rilang", genericError: "Xatolik yuz berdi. Keyinroq urinib ko'ring.",
    copied: 'Havola nusxalandi', locating: 'Aniqlanmoqda…', located: '✓ Joylashuv aniqlandi',
    geoUnsupported: 'Brauzeringiz joylashuvni aniqlay olmaydi. Tumanni tanlang.',
    geoHttps: 'Joylashuv faqat HTTPS orqali ishlaydi. Hozircha tumanni tanlang.',
    geoDenied: 'Joylashuvga ruxsat berilmadi. Brauzer sozlamalaridan ruxsat bering yoki tumanni tanlang.',
    geoFailed: "Joylashuvni aniqlab bo'lmadi. Tumanni tanlang.", mapPicked: '✓ Joylashuv xaritada belgilandi',
    track: 'Buyurtmani kuzatish →', reviews: 'baho', openProfile: 'Profilni ochish →', you: 'Siz',
  }, (function () { var el = document.getElementById('js-i18n'); return el ? JSON.parse(el.textContent) : {}; })());

  // ---------------- Toast ----------------
  function toast(message, type) {
    var stack = document.querySelector('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      stack.setAttribute('aria-live', 'polite');
      document.body.appendChild(stack);
    }
    var el = document.createElement('div');
    el.className = 'toast' + (type ? ' toast--' + type : '');
    el.setAttribute('role', 'status');
    el.textContent = message;
    stack.appendChild(el);
    requestAnimationFrame(function () { requestAnimationFrame(function () { el.classList.add('show'); }); });
    setTimeout(function () {
      el.classList.remove('show');
      setTimeout(function () { el.remove(); }, 300);
    }, type === 'error' ? 6000 : 4500);
  }
  window.toast = toast;

  // ---------------- Mobil menyu ----------------
  var toggle = document.querySelector('.nav__toggle');
  var links = document.querySelector('.nav__links');
  if (toggle && links) {
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    links.addEventListener('click', function (e) {
      if (e.target.closest('a')) { links.classList.remove('is-open'); toggle.setAttribute('aria-expanded', 'false'); }
    });
  }

  // ---------------- Telefon maskasi: +998 (90) 123-45-67 ----------------
  function formatPhone(value) {
    var digits = value.replace(/\D/g, '');
    if (digits.indexOf('998') === 0) { digits = digits.slice(3); }
    digits = digits.slice(0, 9);
    var out = '+998';
    if (digits.length) { out += ' (' + digits.slice(0, 2); }
    if (digits.length >= 2) { out += ')'; }
    if (digits.length > 2) { out += ' ' + digits.slice(2, 5); }
    if (digits.length > 5) { out += '-' + digits.slice(5, 7); }
    if (digits.length > 7) { out += '-' + digits.slice(7, 9); }
    return out;
  }
  function bindPhone(input) {
    if (input.dataset.phoneBound) { return; }
    input.dataset.phoneBound = '1';
    input.setAttribute('inputmode', 'tel');
    input.setAttribute('autocomplete', 'tel');
    if (!input.placeholder) { input.placeholder = '+998 (90) 123-45-67'; }
    input.addEventListener('focus', function () { if (!input.value) { input.value = '+998 '; } });
    input.addEventListener('input', function () {
      var prevLen = input.value.length;
      input.value = formatPhone(input.value);
      if (input.value.length < prevLen && input.value === '+998') { input.value = '+998 '; }
    });
    input.addEventListener('blur', function () { if (input.value.replace(/\D/g, '') === '998') { input.value = ''; } });
  }
  document.querySelectorAll('input[data-phone], input[name="phone"]').forEach(bindPhone);

  // ---------------- Joylashuvni aniqlash ----------------
  // HTTPS talab qilinadi (localhost bundan mustasno) — brauzer cheklovi.
  function setStatus(el, text, kind) {
    if (!el) { return; }
    el.textContent = text;
    el.classList.remove('is-ok', 'is-error');
    if (kind) { el.classList.add('is-' + kind); }
  }

  document.querySelectorAll('[data-geolocate]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var form = btn.closest('form') || document;
      var lat = form.querySelector('[name="lat"], [name="latitude"]');
      var lng = form.querySelector('[name="lng"], [name="longitude"]');
      var district = form.querySelector('[name="district"]');
      var status = form.querySelector('.geo-status');

      if (!('geolocation' in navigator)) {
        setStatus(status, T.geoUnsupported, 'error');
        return;
      }
      if (!window.isSecureContext) {
        setStatus(status, T.geoHttps, 'error');
        return;
      }
      btn.classList.add('is-loading');
      setStatus(status, T.locating);
      navigator.geolocation.getCurrentPosition(function (pos) {
        btn.classList.remove('is-loading');
        if (lat) { lat.value = pos.coords.latitude.toFixed(6); }
        if (lng) { lng.value = pos.coords.longitude.toFixed(6); }
        if (district) { district.value = ''; }
        setStatus(status, T.located + ' (~' + Math.round(pos.coords.accuracy) + ' m)', 'ok');
        document.dispatchEvent(new CustomEvent('location:set', {
          detail: { lat: pos.coords.latitude, lng: pos.coords.longitude, form: form },
        }));
        if (btn.hasAttribute('data-autosubmit') && form.submit) { form.submit(); }
      }, function (err) {
        btn.classList.remove('is-loading');
        var msg = err.code === 1 ? T.geoDenied : T.geoFailed;
        setStatus(status, msg, 'error');
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
    });
  });

  // Tuman tanlansa — eski GPS koordinatasini tozalaymiz (server tumanga qarab topadi)
  document.querySelectorAll('select[name="district"]').forEach(function (sel) {
    sel.addEventListener('change', function () {
      var form = sel.closest('form');
      if (!form || !sel.value) { return; }
      ['lat', 'lng'].forEach(function (n) { var i = form.querySelector('[name="' + n + '"]'); if (i) { i.value = ''; } });
      // Ro'yxatdan o'tish formasida koordinata maydonlarini ham tozalaymiz
      if (form.hasAttribute('data-clear-coords-on-district')) {
        ['latitude', 'longitude'].forEach(function (n) { var i = form.querySelector('[name="' + n + '"]'); if (i) { i.value = ''; } });
      }
      setStatus(form.querySelector('.geo-status'), '');
    });
  });

  // ---------------- AJAX ariza formalari ----------------
  function clearErrors(form) {
    form.querySelectorAll('.is-invalid').forEach(function (el) { el.classList.remove('is-invalid'); el.removeAttribute('aria-invalid'); });
    form.querySelectorAll('.error-message').forEach(function (el) { el.classList.remove('show'); el.textContent = ''; });
    var box = form.querySelector('.results');
    if (box) { box.textContent = ''; }
  }

  function showFieldError(form, name, message) {
    var input = form.querySelector('[name="' + name + '"]');
    if (!input || input.type === 'hidden') {
      var box = form.querySelector('.results');
      if (box) { box.textContent = message; }
      return;
    }
    input.classList.add('is-invalid');
    input.setAttribute('aria-invalid', 'true');
    var holder = input.closest('.field, .check') || input.parentNode;
    var err = holder.querySelector('.error-message');
    if (!err) {
      err = document.createElement('div');
      err.className = 'error-message';
      holder.appendChild(err);
    }
    err.textContent = message;
    err.classList.add('show');
  }

  document.querySelectorAll('.js-request-form').forEach(function (form) {
    form.addEventListener('input', function (e) {
      if (e.target.classList.contains('is-invalid')) {
        e.target.classList.remove('is-invalid');
        var holder = e.target.closest('.field, .check');
        var err = holder && holder.querySelector('.error-message');
        if (err) { err.classList.remove('show'); }
      }
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (form.dataset.submitting) { return; }
      clearErrors(form);

      var btn = form.querySelector('[type="submit"]');
      form.dataset.submitting = '1';
      if (btn) { btn.classList.add('is-loading'); btn.disabled = true; }

      var release = function () {
        delete form.dataset.submitting;
        if (btn) { btn.classList.remove('is-loading'); btn.disabled = false; }
      };

      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      }).then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      }).then(function (r) {
        release();
        if (r.ok && r.data.success) {
          form.reset();
          var done = form.parentNode.querySelector('.form-success');
          if (done) {
            done.querySelector('[data-message]').textContent = r.data.message;
            var track = done.querySelector('[data-track]');
            if (track && r.data.track_url) { track.href = r.data.track_url; track.hidden = false; }
            done.hidden = false;
            form.hidden = true;
          }
          toast(r.data.message, 'success');
          return;
        }
        if (r.data.errors) {
          Object.keys(r.data.errors).forEach(function (name) { showFieldError(form, name, r.data.errors[name]); });
          var first = form.querySelector('.is-invalid');
          if (first) { first.focus(); }
          toast(T.fixErrors, 'error');
          return;
        }
        toast(r.data.message || T.genericError, 'error');
      }).catch(function () {
        release();
        toast(T.network, 'error');
      });
    });
  });

  document.querySelectorAll('[data-reset-form]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var wrap = btn.closest('.form-success');
      var form = wrap && wrap.parentNode.querySelector('.js-request-form');
      if (form) { form.hidden = false; wrap.hidden = true; }
    });
  });

  // ---------------- Nusxa olish ----------------
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.querySelector(btn.dataset.copy);
      if (!input) { return; }
      var done = function () { toast(T.copied, 'success'); };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(input.value).then(done);
      } else {
        input.select();
        document.execCommand('copy');
        done();
      }
    });
  });

  // ---------------- SMS kod (OTP) ----------------
  document.querySelectorAll('[data-otp]').forEach(function (box) {
    var phoneIn = box.querySelector('[data-otp-phone]');
    var codeIn = box.querySelector('[data-otp-code]');
    var err = box.querySelector('[data-otp-error]');
    var debug = box.querySelector('[data-otp-debug]');
    var csrf = box.querySelector('[name="csrfmiddlewaretoken"]').value;
    var sendBtn = box.querySelector('[data-otp-send]');

    function post(url, data) {
      var body = new URLSearchParams(data);
      body.append('purpose', box.dataset.purpose);
      return fetch(url, {
        method: 'POST', body: body, credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
      }).then(function (r) { return r.json(); });
    }

    sendBtn.addEventListener('click', function () {
      err.textContent = '';
      sendBtn.classList.add('is-loading');
      post(box.dataset.sendUrl, { phone: phoneIn.value }).then(function (data) {
        sendBtn.classList.remove('is-loading');
        if (!data.ok) { err.textContent = data.error; return; }
        box.dataset.phoneVerified = data.phone;
        box.querySelector('[data-step="code"]').hidden = false;
        sendBtn.textContent = T.resend;
        codeIn.focus();
        if (data.debug_code) { debug.hidden = false; debug.textContent = T.debugCode + ' ' + data.debug_code; }
      }).catch(function () { sendBtn.classList.remove('is-loading'); err.textContent = T.network; });
    });

    codeIn.addEventListener('input', function () {
      codeIn.value = codeIn.value.replace(/\D/g, '').slice(0, 6);
      if (codeIn.value.length === 6) { box.querySelector('[data-otp-verify]').click(); }
    });

    box.querySelector('[data-otp-verify]').addEventListener('click', function () {
      err.textContent = '';
      post(box.dataset.verifyUrl, { phone: phoneIn.value, code: codeIn.value }).then(function (data) {
        if (!data.ok) { err.textContent = data.error; codeIn.select(); return; }
        if (box.hasAttribute('data-reload')) { window.location.reload(); return; }
        box.querySelectorAll('[data-step]').forEach(function (el) { el.hidden = true; });
        debug.hidden = true;
        box.querySelector('[data-otp-ok]').hidden = false;
        var target = box.dataset.fillTarget && document.querySelector(box.dataset.fillTarget);
        if (target) { target.value = phoneIn.value; target.readOnly = true; }
        document.dispatchEvent(new CustomEvent('otp:verified', { detail: { phone: data.phone } }));
      }).catch(function () { err.textContent = T.network; });
    });
  });

  // ---------------- Yozishma (buyurtma sahifasi) ----------------
  // JS'siz ham ishlaydi (oddiy POST); JS bilan — sahifani yangilamasdan va yangi xabarlarni so'rab turadi.
  document.querySelectorAll('[data-chat]').forEach(function (box) {
    var log = box.querySelector('[data-chat-log]');
    var form = box.querySelector('[data-chat-form]');
    var err = box.querySelector('[data-chat-error]');
    var empty = box.querySelector('[data-chat-empty]');
    var last = 0;
    var busy = false;
    log.querySelectorAll('[data-id]').forEach(function (el) { last = Math.max(last, +el.dataset.id); });
    log.scrollTop = log.scrollHeight;

    function add(m) {
      if (m.id <= last) { return; }
      last = m.id;
      var item = document.createElement('div');
      item.className = 'chat__msg' + (m.mine ? ' chat__msg--mine' : '');
      item.dataset.id = m.id;
      var text = document.createElement('div');
      text.className = 'chat__text';
      text.style.whiteSpace = 'pre-line';
      text.textContent = m.text;   // textContent — foydalanuvchi matni HTML sifatida bajarilmaydi
      var meta = document.createElement('div');
      meta.className = 'chat__meta';
      meta.textContent = (m.mine ? '' : m.sender + ' · ') + m.time;
      item.appendChild(text); item.appendChild(meta);
      log.appendChild(item);
      if (empty) { empty.hidden = true; }
    }

    function apply(data) {
      var near = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
      (data.messages || []).forEach(add);
      if (near) { log.scrollTop = log.scrollHeight; }
    }

    function poll() {
      if (busy || document.hidden) { return; }
      fetch(box.dataset.url + '?after=' + last, {
        credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' },
      }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) { if (d) { apply(d); } })
        .catch(function () {});
    }
    setInterval(poll, 8000);
    document.addEventListener('visibilitychange', poll);

    if (!form) { return; }
    var input = form.querySelector('textarea');
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
    });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var value = input.value.trim();
      if (!value || busy) { return; }
      busy = true; err.textContent = '';
      var body = new URLSearchParams({ text: value, after: last });
      fetch(box.dataset.url, {
        method: 'POST', body: body, credentials: 'same-origin',
        headers: { 'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value,
                   'X-Requested-With': 'XMLHttpRequest' },
      }).then(function (r) { return r.json(); }).then(function (d) {
        busy = false;
        if (d.error) { err.textContent = d.error; return; }
        input.value = '';
        apply(d);
        log.scrollTop = log.scrollHeight;
      }).catch(function () { busy = false; err.textContent = T.network; });
    });
  });

  // ---------------- Rasmni katta ko'rish ----------------
  document.addEventListener('click', function (e) {
    var link = e.target.closest('[data-lightbox]');
    if (!link || !window.HTMLDialogElement) { return; }
    e.preventDefault();
    var dialog = document.createElement('dialog');
    dialog.className = 'lightbox';
    dialog.innerHTML = '<button type="button" aria-label="×">✕</button><img alt="">';
    dialog.querySelector('img').src = link.href;
    dialog.addEventListener('close', function () { dialog.remove(); });
    dialog.addEventListener('click', function (ev) { if (ev.target !== dialog.querySelector('img')) { dialog.close(); } });
    document.body.appendChild(dialog);
    dialog.showModal();
  });

  // ---------------- Yandex xarita ----------------
  // API faqat xarita bor sahifalarda yuklanadi. Yuklanmasa (kalit yo'q, tarmoq),
  // sahifa xaritasiz ham to'liq ishlaydi.
  function initMaps() {
    document.querySelectorAll('[data-map]').forEach(function (el) {
      var dataEl = document.getElementById(el.dataset.map);
      var points = dataEl ? JSON.parse(dataEl.textContent) : [];
      var center = el.dataset.lat ? [parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)]
        : (points.length ? [points[0].lat, points[0].lng] : [41.3111, 69.2797]);

      el.hidden = false;
      var map = new ymaps.Map(el, { center: center, zoom: points.length > 1 ? 11 : 13, controls: ['zoomControl', 'geolocationControl'] });
      map.behaviors.disable('scrollZoom');

      var collection = new ymaps.GeoObjectCollection();
      points.forEach(function (p) {
        collection.add(new ymaps.Placemark([p.lat, p.lng], {
          hintContent: p.name,
          balloonContentHeader: p.name,
          balloonContentBody: (p.categories || []).join(', ') +
            (p.reviews_count ? '<br>★ ' + p.rating.toFixed(1) + ' (' + p.reviews_count + ' ' + T.reviews + ')' : '') +
            (p.distance_km != null ? '<br>' + p.distance_km + ' km' : ''),
          balloonContentFooter: '<a href="' + p.url + '">' + T.openProfile + '</a>',
        }, { preset: 'islands#greenRepairShopIcon' }));
      });
      map.geoObjects.add(collection);

      if (el.dataset.lat && el.dataset.showOrigin) {
        map.geoObjects.add(new ymaps.Placemark(center, { hintContent: T.you }, { preset: 'islands#blueCircleDotIcon' }));
      }
      if (points.length > 1) {
        map.setBounds(collection.getBounds(), { checkZoomRange: true, zoomMargin: 40 });
      }
    });

    // Usta o'z joylashuvini xaritada bosib tanlaydi
    document.querySelectorAll('[data-map-picker]').forEach(function (el) {
      var form = el.closest('form');
      var latIn = form.querySelector('[name="latitude"]');
      var lngIn = form.querySelector('[name="longitude"]');
      var start = latIn.value ? [parseFloat(latIn.value), parseFloat(lngIn.value)] : [41.3111, 69.2797];

      el.hidden = false;
      var map = new ymaps.Map(el, { center: start, zoom: latIn.value ? 14 : 11, controls: ['zoomControl', 'searchControl'] });
      var mark = new ymaps.Placemark(start, {}, { draggable: true, preset: 'islands#greenDotIcon', visible: !!latIn.value });
      map.geoObjects.add(mark);

      function setPoint(coords) {
        mark.geometry.setCoordinates(coords);
        mark.options.set('visible', true);
        latIn.value = coords[0].toFixed(6);
        lngIn.value = coords[1].toFixed(6);
        var district = form.querySelector('[name="district"]');
        if (district) { district.value = ''; }
        setStatus(form.querySelector('.geo-status'), T.mapPicked, 'ok');
      }
      map.events.add('click', function (e) { setPoint(e.get('coords')); });
      mark.events.add('dragend', function () { setPoint(mark.geometry.getCoordinates()); });
      document.addEventListener('location:set', function (e) {
        if (e.detail.form === form) { setPoint([e.detail.lat, e.detail.lng]); map.setCenter([e.detail.lat, e.detail.lng], 15); }
      });
    });
  }

  if (document.querySelector('[data-map], [data-map-picker]') && window.TS_MAPS_URL) {
    var s = document.createElement('script');
    s.src = window.TS_MAPS_URL;
    s.async = true;
    s.onload = function () { if (window.ymaps) { ymaps.ready(initMaps); } };
    document.head.appendChild(s);
  }
})();
