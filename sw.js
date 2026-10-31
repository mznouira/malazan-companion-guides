/* Malazan guides — offline cache.
   Bump CACHE_VERSION after you add or change any file. */
const CACHE_VERSION = 'malazan-v4';
const SHELL = ['./', './index.html', './manifest.webmanifest',
               './books/index.json', './icons/icon-192.png', './icons/icon-512.png',
               './fonts/literata.woff2', './fonts/literata-italic.woff2', './fonts/cinzel.woff2'];

/* cache:'reload' skips the browser's HTTP cache, so a fresh deploy is never precached stale */
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_VERSION)
    .then(c => c.addAll(SHELL.map(u => new Request(u, { cache: 'reload' }))))
    .then(() => self.skipWaiting()));
});

/* Only touch our own caches: every github.io project of one user shares this origin.
   If an older version was cached, this is an update — reload open windows so the
   new version shows now instead of on the next launch. */
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const old = (await caches.keys()).filter(k => k.startsWith('malazan-') && k !== CACHE_VERSION);
    await Promise.all(old.map(k => caches.delete(k)));
    await self.clients.claim();
    if (old.length) {
      const wins = await self.clients.matchAll({ type: 'window' });
      wins.forEach(w => w.navigate(w.url).catch(() => {}));
    }
  })());
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
