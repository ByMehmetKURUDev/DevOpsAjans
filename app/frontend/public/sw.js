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
 * Kimlik taşıyan (Authorization başlıklı) hiçbir isteğe de dokunulmaz.
 *
 * Panel kabuğu (Faz 7M): `/client` ve `/admin` gezinmeleri de önce ağdan
 * alınır; başarılı yanıt (verisiz HTML iskeleti) sorgu dizgisinden bağımsız
 * TEK kopya olarak `PANEL` önbelleğinde tutulur. Bağlantı yokken
 * `/client?sekme=mesajlar` gibi hiç açılmamış bir adres de o iskeletle açılır;
 * panel çevrimdışı olduğunu kendisi gösterir. Veri (/api/) önbelleğe girmez.
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
const SURUM = 'mk-v5';
const KABUK = `${SURUM}-kabuk`;
const VARLIK = `${SURUM}-varlik`;
const PANEL = `${SURUM}-panel`;
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

/** Panel gezinmesi mi? Önbellek anahtarı: sorgusuz yol (`/client`, `/admin`). */
function panelAnahtari(url) {
  const eslesme = /^\/(client|admin)\/?$/.exec(url.pathname);
  return eslesme ? `/${eslesme[1]}` : null;
}

/** Saklanmaya uygun panel iskeleti: aynı kökenden, yönlendirmesiz, 200, HTML. */
function saklanabilirIskelet(yanit) {
  return (
    yanit.status === 200 &&
    yanit.type === 'basic' &&
    !yanit.redirected &&
    (yanit.headers.get('content-type') || '').includes('text/html')
  );
}

/**
 * Panel sayfası — önce ağ; ağ yoksa son başarılı iskelet. Ağ yanıtı ne olursa
 * olsun (hata sayfası dahil) olduğu gibi döner; yalnız düzgün iskelet saklanır.
 */
function panelSayfasi(event, anahtar) {
  return fetch(event.request)
    .then((yanit) => {
      if (saklanabilirIskelet(yanit)) {
        const kopya = yanit.clone();
        // Yazma bitene kadar servis çalışanı ayakta kalsın.
        event.waitUntil(caches.open(PANEL).then((cache) => cache.put(anahtar, kopya)));
      }
      return yanit;
    })
    .catch(() =>
      caches
        .open(PANEL)
        .then((cache) => cache.match(anahtar))
        .then((onbellek) => onbellek || caches.match(CEVRIMDISI))
        .then((yanit) => yanit || Response.error()),
    );
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
  // Kimlikli istek (Authorization) hiçbir zaman önbellekten verilmez, önbelleğe yazılmaz.
  if (request.headers.has('authorization')) return;

  // 1) Sayfalar — önce ağ.
  if (request.mode === 'navigate') {
    // 1a) Panel kabuğu (Faz 7M): tek iskelet kopyası, sorgudan bağımsız.
    const panel = panelAnahtari(url);
    if (panel) {
      event.respondWith(panelSayfasi(event, panel));
      return;
    }
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
// Panel kabuğunu çevrimdışına hazırla (Faz 7M)
// --------------------------------------------------------------------------
//
// İlk ziyarette sayfa, servis çalışanı devreye girmeden yüklendiği için ne
// panel iskeleti ne de giriş betikleri önbelleğe düşüyor. Panel açılınca
// sayfa (`lib/uygulamaKabugu.ts`) yüklediği içerik özetli dosyaların listesini
// gönderiyor; önbellekte olmayanlar burada alınıyor. Yalnız `/client`,
// `/admin` ve `/assets/` altındaki içerik özetli dosyalar kabul edilir —
// `/api/` ya da başka bir adres asla.

self.addEventListener('message', (event) => {
  const veri = event.data;
  if (!veri || veri.tip !== 'panel-iskeleti') return;
  const panel = veri.panel === '/client' || veri.panel === '/admin' ? veri.panel : null;
  const varliklar = (Array.isArray(veri.varliklar) ? veri.varliklar : [])
    .slice(0, 400)
    .map((adres) => {
      try {
        return new URL(String(adres), self.location.origin);
      } catch (e) {
        return null;
      }
    })
    .filter((url) => url && url.origin === self.location.origin && !url.search && icerikOzetliMi(url))
    .map((url) => url.pathname);

  const iskelet = panel
    ? caches.open(PANEL).then((cache) =>
        cache.match(panel).then(
          (mevcut) =>
            mevcut ||
            fetch(panel, { credentials: 'omit' }).then((yanit) =>
              saklanabilirIskelet(yanit) ? cache.put(panel, yanit) : undefined,
            ),
        ),
      )
    : Promise.resolve();
  const dosyalar = caches.open(VARLIK).then((cache) =>
    Promise.all(
      varliklar.map((yol) =>
        cache
          .match(yol)
          .then((mevcut) => mevcut || fetch(yol).then((yanit) => (yanit.ok ? cache.put(yol, yanit) : undefined)))
          .catch(() => undefined),
      ),
    ),
  );
  event.waitUntil(Promise.all([iskelet, dosyalar]).catch(() => undefined));
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
