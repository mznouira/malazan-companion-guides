/* Malazan guides — offline cache.
   Bump CACHE_VERSION after you add or change any file. */
const CACHE_VERSION = 'malazan-v1';
const SHELL = ['./', './index.html', './manifest.webmanifest',
               './books/index.json', './icons/icon-192.png', './icons/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_VERSION)
    .then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE_VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

/* Books and artwork: cache-first, so a book you have read once stays offline.
   index.json: network-first, so newly added books appear as soon as you're online. */
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;

  if (req.url.includes('books/index.json')) {
    e.respondWith(
      fetch(req).then(r => {
        const copy = r.clone();
        caches.open(CACHE_VERSION).then(c => c.put(req, copy));
        return r;
      }).catch(() => caches.match(req))
    );
    return;
  }

  e.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok) {
        const copy = r.clone();
        caches.open(CACHE_VERSION).then(c => c.put(req, copy));
      }
      return r;
    }).catch(() => caches.match('./index.html')))
  );
});
