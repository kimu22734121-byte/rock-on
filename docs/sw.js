// 録音アプリの画面をキャッシュし、電波がない場所でも起動・録音できるようにする。
// API（/api/）とまとめサーバーのファイルは常にネットワークへ。
const CACHE = "rec-v3";
const SHELL = [
  "./", "./index.html", "./manifest.webmanifest", "./icon-180.png", "./icon-192.png", "./icon-512.png",
  "https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.1.6/purify.min.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.includes("/api/")) return;
  // まとめサーバー（別のアドレス）の録音や API はキャッシュしない
  if (url.origin !== location.origin && url.origin !== "https://cdnjs.cloudflare.com") return;
  // 画面はネットワーク優先（更新をすぐ反映）、つながらなければキャッシュ
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
        return res;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
