/*
 * Servis çalışanı.
 *
 * TASARIM KARARI — "bayat sayfa" sorunundan kaçınmak:
 * HTML her zaman önce ağdan alınır (network-first). Panelden içerik
 * değiştirildiğinde ya da yeni sürüm yayınlandığında ziyaretçi eski sayfayı
 * görmez. Ağ yoksa önbellekteki kopya, o da yoksa çevrimdışı sayfası döner.
 *
 * Vite'ın ürettiği dosya adlarında içerik özeti var (app-a1b2c3.js); adı
 * değişmeden içeriği değişemez. Bu yüzden yalnızca onlar cache-first
 * alınabilir — en hızlısı ve en güvenlisi budur.
 *
 * API çağrıları (/api/) hiç dokunulmadan geçer: oturum, panel ve form
 * istekleri önbelleğe alınmamalı.
 */
const SURUM = 'mk-v1';
const KABUK = `${SURUM}-kabuk`;
const VARLIK = `${SURUM}-varlik`;
const CEVRIMDISI = '/cevrimdisi.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(KABUK)
      .then((cache) => cache.addAll([CEVRIMDISI, '/logo192.png']))
      // Çevrimdışı sayfası indirilemezse kurulum yine de tamamlansın:
      // servis çalışanının hiç kurulmaması, tek bir dosyanın eksik
      // olmasından daha kötü.
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((adlar) =>
        Promise.all(adlar.filter((ad) => !ad.startsWith(SURUM)).map((ad) => caches.delete(ad))),
      )
      .then(() => self.clients.claim()),
  );
});

/** İçerik özeti taşıyan, adı değişmeden içeriği değişemeyen dosyalar. */
function icerikOzetliMi(url) {
  return /\/assets\/.+-[A-Za-z0-9_-]{8,}\.(js|css|woff2?)$/.test(url.pathname);
}

/** Görseller: sık değişmiyor, ağ yoksa önbellekten gelmesi iyi. */
function gorselMi(url) {
  return /\.(webp|png|jpg|jpeg|svg|avif|gif|ico)$/.test(url.pathname);
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  // 1) Sayfalar — önce ağ.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((yanit) => {
          const kopya = yanit.clone();
          caches.open(KABUK).then((cache) => cache.put(request, kopya));
          return yanit;
        })
        .catch(() =>
          caches
            .match(request)
            .then((onbellek) => onbellek || caches.match(CEVRIMDISI))
            .then((yanit) => yanit || Response.error()),
        ),
    );
    return;
  }

  // 2) İçerik özetli varlıklar — önce önbellek.
  if (icerikOzetliMi(url) || gorselMi(url)) {
    event.respondWith(
      caches.match(request).then(
        (onbellek) =>
          onbellek ||
          fetch(request).then((yanit) => {
            if (yanit.ok) {
              const kopya = yanit.clone();
              caches.open(VARLIK).then((cache) => cache.put(request, kopya));
            }
            return yanit;
          }),
      ),
    );
  }

  // 3) Geri kalan her şey normal ağ akışına bırakılır.
});
