/* Service worker Meja Pantau IDX.
   - Kerangka aplikasi (HTML, js/*.js, ikon) di-precache → halaman tetap terbuka saat offline.
   - data/*.json: jaringan dulu, jatuh ke cache bila offline.
   - Font Google & pustaka CDN: cache lalu perbarui di latar (stale-while-revalidate).
   Naikkan VERSION saat aset kerangka berubah; cache versi lama dihapus saat activate. */
const VERSION = "20261117b";
const SHELL = `shell-${VERSION}`, DATA = "data-v1", EXT = "ext-v1";
const ASSETS = ["./", "index.html", "favicon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png", "manifest.webmanifest",
  ...["setup","peta","kepemilikan","kalkulator","jurnal","lonjakan","grafikpro","grup","porto","panduan"].map(n => `js/${n}.js?v=${VERSION}`)];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(ASSETS.map(u => new Request(u, {cache: "reload"})))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("shell-") && k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function networkFirst(req, cacheName, key = req){
  const c = await caches.open(cacheName);
  try{
    const r = await fetch(req);
    if(r.ok) c.put(key, r.clone());
    return r;
  }catch(err){
    const hit = await c.match(key, {ignoreSearch: true});
    if(hit) return hit;
    throw err;
  }
}
async function staleWhileRevalidate(req){
  const c = await caches.open(EXT), hit = await c.match(req);
  const net = fetch(req).then(r => { if(r.ok || r.type === "opaque") c.put(req, r.clone()); return r; }).catch(() => hit);
  return hit || net;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if(req.method !== "GET") return;
  const url = new URL(req.url);
  if(url.origin === location.origin){
    if(url.pathname.includes("/data/") && url.pathname.endsWith(".json")){
      // satu entri per file (tanpa ?v=) agar cache tidak menumpuk tiap versi data
      e.respondWith(networkFirst(req, DATA, url.origin + url.pathname));
      return;
    }
    if(req.mode === "navigate"){
      e.respondWith(networkFirst(req, SHELL, new URL("index.html", self.registration.scope).href).catch(() => caches.match("index.html", {ignoreSearch: true})));
      return;
    }
    e.respondWith(caches.match(req).then(hit => hit || fetch(req)));
    return;
  }
  if(/^(fonts\.(googleapis|gstatic)\.com|unpkg\.com|cdn\.jsdelivr\.net)$/.test(url.hostname)){
    e.respondWith(staleWhileRevalidate(req));
  }
});
