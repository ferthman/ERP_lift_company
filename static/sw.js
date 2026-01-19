self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open('liftcrm-v2').then(cache =>
      cache.addAll([
        '/',
        '/mobile',
        '/static/manifest.webmanifest',
        '/static/manifest.mobile.webmanifest',
        '/static/mobile.js',
        '/static/icons/icon-192.png',
        '/static/icons/icon-512.png',
      ])
    )
  );
});
self.addEventListener('fetch', (e) => {
  e.respondWith(caches.match(e.request).then(resp => resp || fetch(e.request)));
});
