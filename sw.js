// Modo sin conexión: guarda la app, los precios y las fotos en el iPhone.
const VERSION = "compras-v1";
const BASE = ["./", "index.html", "manifest.webmanifest", "icon-180.png", "icon-512.png", "prices.json"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(BASE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const esPrecios = url.pathname.endsWith("prices.json");
  const esApp = url.pathname.endsWith("/") || url.pathname.endsWith("index.html");
  if (esPrecios || esApp) {
    // Primero la red (para tener lo último); si no hay conexión, lo guardado.
    e.respondWith(fetch(req).then(r => {
      const copia = r.clone();
      caches.open(VERSION).then(c => c.put(req, copia));
      return r;
    }).catch(() => caches.match(req, { ignoreSearch: true })));
    return;
  }
  // Fotos, iconos y fuentes: primero lo guardado; si no está, se descarga y se guarda.
  e.respondWith(caches.match(req).then(g => g || fetch(req).then(r => {
    if (r.ok || r.type === "opaque") {
      const copia = r.clone();
      caches.open(VERSION).then(c => c.put(req, copia));
    }
    return r;
  })));
});
