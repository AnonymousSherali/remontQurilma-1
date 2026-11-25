{% load static %}/* TechService service worker — versiya {{ version }}.
 * Oflayn: sahifa ochilmasa — /offline/; statik fayllar keshdan.
 * Shaxsiy sahifalar (kabinet, buyurtma) keshlanmaydi. Push bildirishnomalarini ko'rsatadi. */
const CACHE = 'ts-{{ version }}';
const OFFLINE = '/offline/';
const PRECACHE = {{ precache_json|safe }};

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE)));
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    })));
  }
});

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || '{{ SITE.name|escapejs }}', {
    body: data.body || '',
    icon: '{% static "img/icons/icon-192.png" %}',
    badge: '{% static "img/icons/badge-96.png" %}',
    data: { url: data.url || '/' },
    tag: data.url || undefined,
    renotify: true,
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data.url || '/', self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
    for (const w of wins) { if (w.url === target && 'focus' in w) return w.focus(); }
    return self.clients.openWindow(target);
  }));
});
