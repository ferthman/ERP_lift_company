const CACHE_NAME = "liftcrm-shell-v3";
const STATIC_SHELL_URLS = [
  "/static/manifest.webmanifest",
  "/static/manifest.mobile.webmanifest",
  "/static/mobile-2gis.js",
  "/static/mobile.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_SHELL_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)))
      )
      .then(() => self.clients.claim())
  );
});

function isStaticShellRequest(request) {
  if (request.method !== "GET") return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith("/api/")) return false;
  if (url.pathname.startsWith("/uploads/")) return false;
  if (["/", "/admin", "/login", "/logout", "/mobile"].includes(url.pathname)) return false;
  return STATIC_SHELL_URLS.includes(url.pathname);
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (!isStaticShellRequest(request)) {
    event.respondWith(fetch(request));
    return;
  }
  event.respondWith(
    caches.open(CACHE_NAME).then((cache) =>
      cache.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            cache.put(request, response.clone());
          }
          return response;
        });
      })
    )
  );
});
