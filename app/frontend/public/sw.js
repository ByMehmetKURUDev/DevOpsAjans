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
 * API çağrıları (/api/) ve QR kısa adresleri (/q/) hiç dokunulmadan geçer:
 * oturum, panel ve form istekleri ile yönlendirmeler önbelleğe alınmamalı.
 *
 * Web Push: sunucu `{title, body, url}` gönderir; bildirim tıklanınca aynı
 * kökendeki adres açılır (açık bir sekme varsa ona odaklanılır).
 */
/*
 * SÜRÜM NUMARASI — değiştirmeyi unutma.
 *
 * `activate` yalnızca bu önekle BAŞLAMAYAN önbellekleri siliyor. Sayı
 * sabit kaldığı sürece eski önbellek hiç temizlenmiyor: favicon yenilendiği
 * hâlde daha önce siteye girmiş herkeste aylarca eskisi göründü, sebebi
 * buydu. Önbelleğe alınan bir varlığın davranışı değiştiğinde bu sayı
 * artırılmalı.
 */
const SURUM = 'mk-v4';
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
  // Faz 4Q: QR / kısa link yönlendirmeleri (`/q/<kod>`) her zaman doğrudan
  // ağa gitsin: önbelleğe alınmasın, çevrimdışıyken eski bir yönlendirme dönmesin.
  if (url.pathname.startsWith('/q/')) return;

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
  // Adı içeriğine bağlı olduğu için önbellekteki kopya asla yanlış olamaz.
  if (icerikOzetliMi(url)) {
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
    return;
  }

  // 3) Görseller — önbellekten göster, ARKADA tazele.
  //
  // Burası önceden görselleri de "önce önbellek, bulursa ağa hiç çıkma"
  // kuralına sokuyordu. Görsellerin adında içerik özeti yok: favicon,
  // logo ya da kapak görseli değiştiğinde adres aynı kaldığı için daha
  // önce siteye girmiş herkes eski dosyayı görmeye devam ediyordu ve
  // bunun süresi yoktu. Şimdi kopya anında dönüyor (hız aynı), ama aynı
  // anda ağdan tazesi alınıp önbelleğe yazılıyor; ikinci ziyarette yenisi
  // görünüyor.
  if (gorselMi(url)) {
    event.respondWith(
      caches.match(request).then((onbellek) => {
        const agIstegi = fetch(request)
          .then((yanit) => {
            if (yanit.ok) {
              const kopya = yanit.clone();
              caches.open(VARLIK).then((cache) => cache.put(request, kopya));
            }
            return yanit;
          })
          .catch(() => onbellek);

        // Önbellekten yanıt verirken bile tazeleme bitene kadar servis
        // çalışanı ayakta kalsın.
        if (onbellek) event.waitUntil(agIstegi);
        return onbellek || agIstegi;
      }),
    );
    return;
  }

  // 4) Geri kalan her şey normal ağ akışına bırakılır.
});

// --------------------------------------------------------------------------
// Web Push
// --------------------------------------------------------------------------

/** Yalnız aynı kökenli adres; başka bir yere yönlendirme yapılmaz. */
function guvenliAdres(ham) {
  try {
    const adres = new URL(ham || '/', self.location.origin);
    return adres.origin === self.location.origin ? adres.href : self.location.origin + '/';
  } catch (e) {
    return self.location.origin + '/';
  }
}

self.addEventListener('push', (event) => {
  let veri = {};
  try {
    veri = event.data ? event.data.json() : {};
  } catch (e) {
    veri = { body: event.data ? event.data.text() : '' };
  }
  const baslik = veri.title || 'mehmetkuru.dev';
  event.waitUntil(
    self.registration.showNotification(baslik, {
      body: veri.body || '',
      icon: '/logo192.png',
      badge: '/favicon-32.png',
      data: { url: guvenliAdres(veri.url) },
      // Aynı adrese giden art arda bildirimler üst üste yığılmasın.
      tag: veri.url || undefined,
      renotify: Boolean(veri.url),
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const hedef = guvenliAdres(event.notification.data && event.notification.data.url);
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((pencereler) => {
      for (const pencere of pencereler) {
        if (pencere.url === hedef && 'focus' in pencere) return pencere.focus();
      }
      for (const pencere of pencereler) {
        if (new URL(pencere.url).origin === self.location.origin && 'navigate' in pencere) {
          return pencere.focus().then((p) => (p || pencere).navigate(hedef));
        }
      }
      return self.clients.openWindow ? self.clients.openWindow(hedef) : undefined;
    }),
  );
});
