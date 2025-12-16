self.addEventListener('install', (e) => {
  e.waitUntil(caches.open('liftcrm-v1').then(cache => cache.addAll(['/','/static/manifest.webmanifest'])));
});
self.addEventListener('fetch', (e) => {
  e.respondWith(caches.match(e.request).then(resp => resp || fetch(e.request)));
});
