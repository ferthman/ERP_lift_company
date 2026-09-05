const CACHE_NAME = "liftcrm-shell-v7";
const STATIC_SHELL_URLS = [
  "/mobile-shell", "/static/manifest.webmanifest", "/static/manifest.mobile.webmanifest",
  "/static/mobile-2gis.js", "/static/mobile.js", "/static/mobile.css", "/static/crm.css",
  "/static/vendor/tailwind.css", "/static/icons/icon-192.png", "/static/icons/icon-512.png",
];
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_SHELL_URLS)).then(()=>self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then(names=>Promise.all(names.filter(name=>name.startsWith('liftcrm-shell-')&&name!==CACHE_NAME).map(name=>caches.delete(name)))).then(()=>self.clients.claim()));
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
  const request=event.request, url=new URL(request.url);
  if(request.mode==='navigate' && url.origin===self.location.origin && url.pathname==='/mobile'){
    // Cache only the public shell, never an authenticated HTML response.
    event.respondWith(fetch(request).catch(()=>caches.open(CACHE_NAME).then(cache=>cache.match('/mobile-shell'))));
    return;
  }
  if(!isStaticShellRequest(request)) {event.respondWith(fetch(request)); return;}
  event.respondWith(caches.open(CACHE_NAME).then(async cache=>(await cache.match(url.pathname))||fetch(request)));
});
