// 離線快取：App 本體 stale-while-revalidate，stocks-latest.json network-first（失敗回傳上次快取）
// 改版時調整 VERSION，activate 會清掉舊快取。路徑一律相對，才能部署在 GitHub Pages 子路徑。
const VERSION = 'v2';
const CACHE = `stock-agent-${VERSION}`;
const PRECACHE = ['./', 'index.html', 'app.js', 'style.css', 'manifest.json', 'icon.svg', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// 快取回應加上標記，讓頁面知道這是離線資料
function markCached(resp) {
  const headers = new Headers(resp.headers);
  headers.set('x-sw-cache', '1');
  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers });
}

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;

  if (url.pathname.endsWith('/stocks-latest.json')) {
    e.respondWith(
      fetch(req)
        .then(resp => {
          if (resp.ok) { const copy = resp.clone(); caches.open(CACHE).then(c => c.put(url.pathname, copy)); }
          return resp;
        })
        .catch(() => caches.match(url.pathname).then(hit => hit ? markCached(hit) : Response.error()))
    );
    return;
  }

  e.respondWith(
    caches.open(CACHE).then(c => c.match(req, { ignoreSearch: true }).then(hit => {
      const refresh = fetch(req).then(resp => { if (resp.ok) c.put(req, resp.clone()); return resp; });
      if (hit) { refresh.catch(() => {}); return hit; }
      return refresh;
    }))
  );
});
