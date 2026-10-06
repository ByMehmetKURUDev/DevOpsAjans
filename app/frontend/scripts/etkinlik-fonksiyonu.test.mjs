/**
 * Faz 6E — `functions/etkinlik/[[yol]].js` ve `functions/etkinlikler/[slug].js` (Cloudflare Pages
 * Function) birim testi. Çalıştırma: `node --test scripts/etkinlik-fonksiyonu.test.mjs` (pytest
 * `tests/backend/test_etkinlik_fonksiyon.py` üzerinden de çağırıyor).
 *
 * Node'da `HTMLRewriter` yok: randevu testindeki küçük taklit. `fetch` ve `env.ASSETS` de taklit.
 * Doğrulananlar: OG/twitter/canonical/robots, noindex varsayılanı, indekslenebilir etkinlikte
 * Event JSON-LD (güvenli kaçış, online bağlantı yok) ve CSP başlığı, bilet/görevli/panel
 * okutucuda arka uca gidilmemesi + noindex + no-referrer, kamera izninin YALNIZ okutucuda açılması,
 * vekil imzası, gömülü pencerede çerçeve izni, 404/410, arka uç hatasında kabuk, liste sayfası.
 */
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

// ---------------------------------------------------------------------------
// HTMLRewriter taklidi (yalnız testte)
// ---------------------------------------------------------------------------
const BOS_ETIKETLER = new Set(['meta', 'link', 'br', 'img', 'input', 'hr']);

function oznitelikleriCoz(metin) {
  const sonuc = new Map();
  const desen = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
  let e;
  while ((e = desen.exec(metin))) sonuc.set(e[1].toLowerCase(), e[2] ?? e[3] ?? e[4] ?? '');
  return sonuc;
}

function metinKacis(m) {
  return String(m).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function kapanisBul(html, ad, bas) {
  const desen = new RegExp(`<(/?)${ad}\\b[^>]*>`, 'gi');
  desen.lastIndex = bas;
  let derinlik = 1;
  let e;
  while ((e = desen.exec(html))) {
    derinlik += e[1] ? -1 : 1;
    if (derinlik === 0) return { bas: e.index, son: desen.lastIndex };
  }
  return null;
}

function uygula(html, secici, isleyici) {
  const [ad, kimlik] = secici.split('#');
  const desen = new RegExp(`<${ad}\\b([^>]*)>`, 'gi');
  let cikti = '';
  let konum = 0;
  let e;
  while ((e = desen.exec(html))) {
    const oz = oznitelikleriCoz(e[1]);
    if (kimlik && oz.get('id') !== kimlik) continue;
    const acilisSon = desen.lastIndex;
    const bos = BOS_ETIKETLER.has(ad) || e[1].trim().endsWith('/');
    const kapanis = bos ? null : kapanisBul(html, ad, acilisSon);
    let silindi = false;
    let ic = null;
    let ekle = '';
    const eleman = {
      tagName: ad,
      getAttribute: (a) => (oz.has(a.toLowerCase()) ? oz.get(a.toLowerCase()) : null),
      setAttribute: (a, d) => oz.set(a.toLowerCase(), String(d)),
      remove: () => {
        silindi = true;
      },
      setInnerContent: (m, s = {}) => {
        ic = s.html ? m : metinKacis(m);
      },
      append: (m, s = {}) => {
        ekle += s.html ? m : metinKacis(m);
      },
    };
    isleyici.element(eleman);
    const tamSon = kapanis ? kapanis.son : acilisSon;
    cikti += html.slice(konum, e.index);
    if (!silindi) {
      const ozMetni = [...oz].map(([a, d]) => (d === '' && !['content', 'href'].includes(a) ? ` ${a}` : ` ${a}="${d}"`)).join('');
      cikti += `<${ad}${ozMetni}>`;
      if (kapanis) {
        cikti += (ic ?? html.slice(acilisSon, kapanis.bas)) + ekle + html.slice(kapanis.bas, kapanis.son);
      }
    }
    konum = tamSon;
    desen.lastIndex = tamSon;
  }
  return cikti + html.slice(konum);
}

class HTMLRewriterTaklidi {
  constructor() {
    this.kurallar = [];
  }
  on(secici, isleyici) {
    this.kurallar.push([secici, isleyici]);
    return this;
  }
  transform(yanit) {
    const kurallar = this.kurallar;
    const govde = yanit.text().then((html) => kurallar.reduce((h, [s, i]) => uygula(h, s, i), html));
    return new Response(
      new ReadableStream({
        async start(denetci) {
          denetci.enqueue(new TextEncoder().encode(await govde));
          denetci.close();
        },
      }),
      { status: yanit.status, headers: yanit.headers }
    );
  }
}
globalThis.HTMLRewriter = HTMLRewriterTaklidi;

const { onRequest, yolCoz, ZAMAN_ASIMI_MS, IZINLER_KAMERA } = await import('../functions/etkinlik/[[yol]].js');
const liste = await import('../functions/etkinlikler/[slug].js');

const KABUK =
  '<!doctype html><html lang="tr"><head><meta charset="UTF-8" />' +
  '<title>Web Geliştirme | By Mehmet KURU Dev</title>' +
  '<link rel="canonical" href="https://mehmetkuru.dev/">' +
  '<link rel="alternate" hreflang="en" href="https://mehmetkuru.dev/en">' +
  '<meta name="description" content="Ajans ana sayfası">' +
  '<meta property="og:title" content="Ajans"><meta name="robots" content="index, follow">' +
  '<script type="application/ld+json">{"@type":"Organization"}</script>' +
  '<script type="module" src="/assets/index-abc.js"></script>' +
  '</head><body><div id="root"><div>Ana sayfa içeriği</div></div></body></html>';

const gercekFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = gercekFetch;
});

function ortam(ek = {}) {
  return {
    API_ORIGIN: 'https://api.ornek.dev/',
    ASSETS: { fetch: async () => new Response(KABUK, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8', etag: '"k"' } }) },
    ...ek,
  };
}

function arkaUc(yanit) {
  const cagrilar = [];
  globalThis.fetch = async (adres, secenek = {}) => {
    cagrilar.push({ adres: String(adres), basliklar: new Headers(secenek.headers || {}) });
    return typeof yanit === 'function' ? yanit(String(adres)) : yanit.clone();
  };
  return cagrilar;
}

const json = (veri, durum = 200) => new Response(JSON.stringify(veri), { status: durum, headers: { 'content-type': 'application/json' } });

const JSONLD = {
  '@context': 'https://schema.org', '@type': 'Event', name: 'Yapay zekâ </script><script>alert(1)</script> atölyesi',
  startDate: '2026-11-05T10:00:00+03:00', endDate: '2026-11-05T17:00:00+03:00',
  eventAttendanceMode: 'https://schema.org/MixedEventAttendanceMode', eventStatus: 'https://schema.org/EventScheduled',
  location: [{ '@type': 'Place', name: 'Ofis', address: 'Kadıköy' }, { '@type': 'VirtualLocation', url: 'https://mehmetkuru.dev/etkinlik/ai-atolyesi' }],
  organizer: { '@type': 'Organization', name: 'By Mehmet KURU Dev', url: 'https://mehmetkuru.dev' },
  offers: [{ '@type': 'Offer', name: 'Standart', price: '0.00', priceCurrency: 'TRY', availability: 'https://schema.org/InStock' }],
};

const OZET = {
  slug: 'ai-atolyesi', baslik: 'Yapay zekâ "atölyesi" <2026>', aciklama: 'Uygulamalı otomasyon atölyesi.', dil: 'tr',
  gorsel: 'https://mehmetkuru.dev/api/v1/etkinlik/gorsel/abc', renk: '#0f766e', indekslenebilir: false,
  adres_url: 'https://mehmetkuru.dev/etkinlik/ai-atolyesi', baslangic: '2026-11-05T07:00:00Z', bitis: '2026-11-05T14:00:00Z',
  saat_dilimi: 'Europe/Istanbul', durum: 'yayinda', jsonld: null,
};

async function cagir(yol, env = ortam(), method = 'GET', basliklar = {}) {
  const url = new URL(`https://mehmetkuru.dev${yol}`);
  const parcalar = url.pathname.split('/').slice(2).filter(Boolean);
  return onRequest({ request: new Request(url, { method, headers: basliklar }), env, params: { yol: parcalar } });
}

const etiket = (html, desen) => (html.match(desen) || [])[1];
const GOREVLI = `12-1-1793000000-${'c'.repeat(32)}`;
const SIPARIS = `34-${'d'.repeat(32)}`;

test('yol çözümü: sayfa, bilet, görevli, panel okutucu, ayrılmış adlar, geçersiz', () => {
  assert.deepEqual(yolCoz(['ai-atolyesi']), { tur: 'sayfa', slug: 'ai-atolyesi' });
  assert.deepEqual(yolCoz(['AI-Atolyesi']), { tur: 'sayfa', slug: 'ai-atolyesi' });
  assert.deepEqual(yolCoz(['ai-atolyesi', 'bilet', SIPARIS]), { tur: 'bilet', slug: 'ai-atolyesi', gecerli: true });
  assert.deepEqual(yolCoz(['ai-atolyesi', 'bilet', 'kotu']), { tur: 'bilet', slug: 'ai-atolyesi', gecerli: false });
  assert.deepEqual(yolCoz(['giris', GOREVLI]), { tur: 'giris', gecerli: true });
  assert.deepEqual(yolCoz(['giris', SIPARIS]), { tur: 'giris', gecerli: false });
  assert.deepEqual(yolCoz(['okut', '42']), { tur: 'okut', gecerli: true });
  assert.deepEqual(yolCoz(['okut', 'x']), { tur: 'okut', gecerli: false });
  for (const kotu of [['giris'], ['okut'], ['bilet'], ['ab'], ['-x'], [], undefined, ['a', 'b', 'c', 'd']]) {
    assert.deepEqual(yolCoz(kotu), { tur: 'yok' }, JSON.stringify(kotu));
  }
});

test('etkinlik sayfası: OG/twitter/canonical/robots; noindex varsayılan; JSON-LD yok; vekil imzası', async () => {
  const cagrilar = arkaUc(json(OZET));
  const y = await cagir('/etkinlik/ai-atolyesi', ortam({ VEKIL_ANAHTARI: 'gizli-vekil' }), 'GET', { 'CF-Connecting-IP': '198.51.100.7', 'X-MK-Istemci-IP': '1.1.1.1' });
  const html = await y.text();
  assert.equal(cagrilar.length, 1);
  assert.equal(cagrilar[0].adres, 'https://api.ornek.dev/api/v1/etkinlik/ai-atolyesi/ozet');
  assert.equal(cagrilar[0].basliklar.get('x-mk-vekil-anahtari'), 'gizli-vekil');
  assert.equal(cagrilar[0].basliklar.get('x-mk-istemci-ip'), '198.51.100.7');
  assert.equal(y.status, 200);
  assert.equal(etiket(html, /<meta property="og:title" content="([^"]*)"/), 'Yapay zekâ &quot;atölyesi&quot; &lt;2026&gt; | Etkinlik');
  assert.equal(etiket(html, /<link rel="canonical" href="([^"]*)"/), 'https://mehmetkuru.dev/etkinlik/ai-atolyesi');
  assert.equal(etiket(html, /<meta property="og:image" content="([^"]*)"/), 'https://mehmetkuru.dev/api/v1/etkinlik/gorsel/abc');
  assert.equal(etiket(html, /<meta name="twitter:card" content="([^"]*)"/), 'summary_large_image');
  assert.equal(etiket(html, /<meta name="description" content="([^"]*)"/), 'Uygulamalı otomasyon atölyesi.');
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'noindex, nofollow');
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('x-frame-options'), 'SAMEORIGIN');
  assert.match(y.headers.get('permissions-policy'), /camera=\(\)/);
  assert.match(y.headers.get('content-security-policy') || '', /script-src 'self'/);
  assert.ok(!html.includes('hreflang'), 'hreflang kaldırılmalı');
  assert.ok(!html.includes('application/ld+json'), 'ana sayfa JSON-LD kaldırılmalı, etkinlik JSON-LD yok');
  assert.ok(!html.includes('Ana sayfa içeriği'), 'iskelet konmalı');
  assert.equal((html.match(/<meta name="robots"/g) || []).length, 1);
});

test('indekslenebilir etkinlik: index + Event JSON-LD (kaçışlı, tek blok); gömülüde yine noindex', async () => {
  arkaUc(json({ ...OZET, indekslenebilir: true, jsonld: JSONLD }));
  const y = await cagir('/etkinlik/ai-atolyesi');
  const html = await y.text();
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'index, follow');
  assert.equal(y.headers.get('x-robots-tag'), null);
  const bloklar = html.match(/<script type="application\/ld\+json" data-mk-etkinlik>([\s\S]*?)<\/script>/g) || [];
  assert.equal(bloklar.length, 1);
  assert.equal((html.match(/application\/ld\+json/g) || []).length, 1);
  const ic = bloklar[0].replace(/^<script[^>]*>/, '').replace(/<\/script>$/, '');
  assert.ok(!ic.includes('<'), 'JSON-LD içinde çıplak < olmamalı (</script> kaçışı)');
  const veri = JSON.parse(ic);
  assert.equal(veri['@type'], 'Event');
  assert.equal(veri.name, JSONLD.name);
  assert.equal(veri.startDate, '2026-11-05T10:00:00+03:00');
  // CSP başlığı korunuyor (JSON-LD veri bloğu; satır içi betik izni gerekmiyor)
  assert.ok(!/unsafe-inline/.test((y.headers.get('content-security-policy') || '').split(';').find((x) => x.trim().startsWith('script-src')) || ''));
  arkaUc(json({ ...OZET, indekslenebilir: true, jsonld: JSONLD }));
  const g = await cagir('/etkinlik/ai-atolyesi?gomulu=1');
  const gh = await g.text();
  assert.equal(g.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.ok(!gh.includes('data-mk-etkinlik'));
  assert.equal(g.headers.get('x-frame-options'), null);
  assert.match(g.headers.get('content-security-policy') || '', /frame-ancestors \*(;|$)/);
});

test('Arapça ve dil parametresi: lang/dir, og:locale', async () => {
  arkaUc(json({ ...OZET, dil: 'ar' }));
  const html = await (await cagir('/etkinlik/ai-atolyesi')).text();
  assert.match(html, /<html lang="ar" dir="rtl">/);
  assert.match(html, /<meta property="og:locale" content="ar_AR">/);
  assert.match(html, /\| فعالية<\/title>/);
  arkaUc(json(OZET));
  const en = await (await cagir('/etkinlik/ai-atolyesi?dil=en')).text();
  assert.match(en, /<html lang="en" dir="ltr">/);
  assert.match(en, /\| Event<\/title>/);
});

test('bilet sayfası: arka uca gidilmez, kişisel bilgi yok, noindex, no-referrer', async () => {
  const cagrilar = arkaUc(json(OZET));
  const y = await cagir(`/etkinlik/ai-atolyesi/bilet/${SIPARIS}`);
  const html = await y.text();
  assert.equal(cagrilar.length, 0);
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('referrer-policy'), 'no-referrer');
  assert.match(y.headers.get('permissions-policy'), /camera=\(\)/);
  assert.match(html, /<title>Biletiniz \| By Mehmet KURU Dev<\/title>/);
  assert.ok(!html.includes('og:title'));
  assert.equal((await cagir('/etkinlik/ai-atolyesi/bilet/kotu')).status, 404);
});

test('görevli ve panel okutucu: kamera izni YALNIZ burada, arka uca gidilmez, noindex, no-referrer', async () => {
  const cagrilar = arkaUc(json(OZET));
  for (const yol of [`/etkinlik/giris/${GOREVLI}`, '/etkinlik/okut/42?mod=yonetici']) {
    const y = await cagir(yol);
    const html = await y.text();
    assert.equal(y.status, 200, yol);
    assert.equal(y.headers.get('permissions-policy'), IZINLER_KAMERA);
    assert.match(IZINLER_KAMERA, /camera=\(self\)/);
    assert.match(IZINLER_KAMERA, /microphone=\(\)/);
    assert.equal(y.headers.get('referrer-policy'), 'no-referrer');
    assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
    assert.equal(y.headers.get('cache-control'), 'no-store');
    assert.match(html, /<title>Kapı girişi \| By Mehmet KURU Dev<\/title>/);
  }
  assert.equal(cagrilar.length, 0);
  assert.equal((await cagir('/etkinlik/giris/kotu-jeton')).status, 404);
  assert.equal((await cagir('/etkinlik/okut/abc')).status, 404);
  // Okutucu dışındaki her yanıtta kamera kapalı
  assert.match((await cagir('/etkinlik/okut')).headers.get('permissions-policy'), /camera=\(\)/);
});

test('404 / 410 durumları ve geçersiz yol', async () => {
  arkaUc(json({ detail: { kod: 'etkinlik_yok' } }, 404));
  assert.equal((await cagir('/etkinlik/yok-boyle')).status, 404);
  arkaUc(json({ detail: { kod: 'etkinlik_pasif' } }, 410));
  const y = await cagir('/etkinlik/kapali-etkinlik');
  assert.equal(y.status, 410);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  const cagrilar = arkaUc(json(OZET));
  assert.equal((await cagir('/etkinlik/A_B')).status, 404);
  assert.equal((await cagir('/etkinlik/giris')).status, 404);
  assert.equal(cagrilar.length, 0);
});

test('arka uç hatası ya da zaman aşımı: kabuk + noindex (200); kabuk yoksa sade sayfa; POST 405', async () => {
  arkaUc(json({}, 503));
  const y = await cagir('/etkinlik/ai-atolyesi');
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  globalThis.fetch = (adres, secenek) => new Promise((_, ret) => secenek.signal.addEventListener('abort', () => ret(new Error('abort'))));
  const bas = Date.now();
  const z = await cagir('/etkinlik/ai-atolyesi');
  assert.equal(z.status, 200);
  assert.ok(Date.now() - bas < ZAMAN_ASIMI_MS + 1500);
  assert.equal((await cagir('/etkinlik/ai-atolyesi', ortam(), 'POST')).status, 405);
  const s = await cagir('/etkinlik/ai-atolyesi', { API_ORIGIN: 'https://api.ornek.dev' });
  assert.equal(s.status, 502);
  assert.match(await s.text(), /Etkinlik sayfası şu an açılamadı/);
});

test('etkinlik listesi: başlık/açıklama/canonical, her zaman noindex; 404; gömülü çerçeve izni', async () => {
  const cagrilar = arkaUc(json({ slug: 'ajans-etkinlikleri', baslik: 'Ajans <Etkinlikleri>', aciklama: '', adres_url: 'https://mehmetkuru.dev/etkinlikler/ajans-etkinlikleri', etkinlikler: [{}, {}], gecmis: false }));
  const istek = (yol, method = 'GET') => {
    const url = new URL(`https://mehmetkuru.dev${yol}`);
    return liste.onRequest({ request: new Request(url, { method }), env: ortam(), params: { slug: url.pathname.split('/')[2] } });
  };
  const y = await istek('/etkinlikler/ajans-etkinlikleri');
  const html = await y.text();
  assert.equal(cagrilar[0].adres, 'https://api.ornek.dev/api/v1/etkinlikler/ajans-etkinlikleri');
  assert.equal(y.status, 200);
  assert.match(html, /<title>Ajans &lt;Etkinlikleri&gt; \| Etkinlikler<\/title>/);
  assert.equal(etiket(html, /<meta name="description" content="([^"]*)"/), 'Ajans &lt;Etkinlikleri&gt; — Etkinlikler (2)');
  assert.equal(etiket(html, /<link rel="canonical" href="([^"]*)"/), 'https://mehmetkuru.dev/etkinlikler/ajans-etkinlikleri');
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal((await istek('/etkinlikler/A_B')).status, 404);
  arkaUc(json({ detail: { kod: 'liste_yok' } }, 404));
  assert.equal((await istek('/etkinlikler/yok-liste')).status, 404);
  arkaUc(json({ slug: 'x-y-z', baslik: 'X', etkinlikler: [] }));
  const g = await istek('/etkinlikler/x-y-z?gomulu=1');
  assert.equal(g.headers.get('x-frame-options'), null);
  assert.equal((await istek('/etkinlikler/x-y-z', 'POST')).status, 405);
});
