/**
 * Faz 4M — `functions/menu/[slug].js` (Cloudflare Pages Function) için birim testi.
 *
 * Çalıştırma: `node --test scripts/menu-fonksiyonu.test.mjs` (arka uç pytest'i de
 * `tests/backend/test_qr_menu_fonksiyon.py` üzerinden çağırıyor).
 *
 * Node'da `HTMLRewriter` yok: aşağıda Function'ın kullandığı alt küme (etiket adı ve
 * `etiket#id` seçicileri; `getAttribute`, `setAttribute`, `remove`, `setInnerContent`,
 * `append`) için küçük bir taklit var. `fetch` ve `env.ASSETS` de taklit.
 * Doğrulananlar: OG/twitter/canonical/robots etiketleri, ürün parametresi, dil,
 * ana sayfaya ait hreflang/JSON-LD'nin kaldırılması, `#root` iskeleti, noindex
 * varsayılanı, 404/410, arka uç hatası ve zaman aşımında kabuk.
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

const { onRequest, kacis, ZAMAN_ASIMI_MS } = await import('../functions/menu/[slug].js');

// ---------------------------------------------------------------------------
// Ortak taklitler
// ---------------------------------------------------------------------------
const KABUK =
  '<!doctype html><html lang="tr"><head><meta charset="UTF-8" />' +
  '<meta name="viewport" content="width=device-width, initial-scale=1.0" />' +
  '<title>Web Geliştirme | By Mehmet KURU Dev</title>' +
  '<link rel="canonical" href="https://mehmetkuru.dev/">' +
  '<link rel="alternate" hreflang="en" href="https://mehmetkuru.dev/en">' +
  '<meta name="description" content="Ajans ana sayfası">' +
  '<meta property="og:title" content="Ajans"><meta property="og:image" content="https://mehmetkuru.dev/og.webp">' +
  '<meta name="twitter:card" content="summary_large_image"><meta name="robots" content="index, follow">' +
  '<script type="application/ld+json">{"@type":"Organization"}</script>' +
  '<script type="module" src="/assets/index-abc.js"></script>' +
  '</head><body><div id="root"><div class="ana"><div>Ana sayfa içeriği</div></div></div></body></html>';

const gercekFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = gercekFetch;
});

function ortam(ek = {}) {
  const kabukCagrilari = [];
  return {
    kabukCagrilari,
    env: {
      API_ORIGIN: 'https://mehmetkuru-api.onrender.com/',
      ASSETS: {
        fetch: async (istek) => {
          kabukCagrilari.push(String(istek.url));
          return new Response(KABUK, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8', etag: '"kabuk"' } });
        },
      },
      ...ek,
    },
  };
}

function arkaUc(yanit) {
  const cagrilar = [];
  globalThis.fetch = async (adres, secenek) => {
    cagrilar.push({ adres: String(adres), secenek });
    return typeof yanit === 'function' ? yanit(String(adres), secenek) : yanit.clone();
  };
  return cagrilar;
}

const OZET = {
  slug: 'cinar-kafe',
  duzen: 'menu',
  ad: 'Çınar "Kafe" & <Bistro>',
  aciklama: 'Taze kahve ve ev yapımı tatlılar.',
  dil: 'tr',
  diller: ['tr', 'en'],
  gorsel: 'https://mehmetkuru.dev/api/v1/menu-gorsel/abc?b=b',
  tema_rengi: '#0f766e',
  indekslenebilir: false,
  adres_url: 'https://mehmetkuru.dev/menu/cinar-kafe',
  urun: null,
};

const json = (veri, durum = 200) =>
  new Response(JSON.stringify(veri), { status: durum, headers: { 'content-type': 'application/json' } });

async function cagir(yol, env, method = 'GET') {
  const url = new URL(`https://mehmetkuru.dev${yol}`);
  const slug = url.pathname.split('/')[2] ?? '';
  return onRequest({ request: new Request(url, { method }), env, params: { slug } });
}

const etiket = (html, desen) => (html.match(desen) || [])[1];

// ---------------------------------------------------------------------------
test('OG, twitter, canonical ve robots menüye göre yazılır; ana sayfanınkiler kalkar', async () => {
  const cagrilar = arkaUc(json(OZET));
  const { env, kabukCagrilari } = ortam();
  const y = await cagir('/menu/cinar-kafe', env);
  const html = await y.text();

  assert.equal(cagrilar.length, 1);
  assert.equal(cagrilar[0].adres, 'https://mehmetkuru-api.onrender.com/api/v1/menu/cinar-kafe/ozet');
  assert.equal(kabukCagrilari[0], 'https://mehmetkuru.dev/');
  assert.equal(y.status, 200);
  assert.equal(etiket(html, /<title>([^<]*)<\/title>/), kacis('Çınar "Kafe" & <Bistro> | Menü').replace(/&quot;/g, '"').replace(/&#39;/g, "'"));
  assert.match(html, /<meta name="description" content="Taze kahve ve ev yapımı tatlılar\.">/);
  assert.match(html, /<meta property="og:title" content="Çınar &quot;Kafe&quot; &amp; &lt;Bistro&gt; \| Menü">/);
  assert.match(html, /<meta property="og:image" content="https:\/\/mehmetkuru\.dev\/api\/v1\/menu-gorsel\/abc\?b=b">/);
  assert.match(html, /<meta property="og:url" content="https:\/\/mehmetkuru\.dev\/menu\/cinar-kafe">/);
  assert.match(html, /<meta property="og:type" content="website">/);
  assert.match(html, /<meta property="og:locale" content="tr_TR">/);
  assert.match(html, /<meta name="twitter:card" content="summary_large_image">/);
  assert.match(html, /<link rel="canonical" href="https:\/\/mehmetkuru\.dev\/menu\/cinar-kafe">/);
  // Varsayılan: arama motorlarına kapalı.
  assert.match(html, /<meta name="robots" content="noindex, nofollow">/);
  assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  // Ana sayfaya ait etiketler tek kopya bile kalmadı.
  assert.equal((html.match(/rel="canonical"/g) || []).length, 1);
  assert.equal((html.match(/name="description"/g) || []).length, 1);
  assert.equal((html.match(/name="robots"/g) || []).length, 1);
  assert.doesNotMatch(html, /hreflang/);
  assert.doesNotMatch(html, /application\/ld\+json/);
  assert.doesNotMatch(html, /Ajans ana sayfası|og\.webp|Ana sayfa içeriği/);
  // Uygulama betiği duruyor; #root içinde iskelet var.
  assert.match(html, /<script type="module" src="\/assets\/index-abc\.js"><\/script>/);
  assert.match(html, /<div id="root"><div style="min-height:100vh[^"]*">.*border:3px solid #0f766e/);
  // Güvenlik başlıkları; kabuğun ETag'i taşınmıyor.
  assert.equal(y.headers.get('X-Content-Type-Options'), 'nosniff');
  assert.equal(y.headers.get('etag'), null);
});

test('ürün parametresi: başlık, açıklama, görsel, og:type product ve canonical ?urun=', async () => {
  const cagrilar = arkaUc(json({
    ...OZET,
    urun: { id: 42, ad: 'Latte', aciklama: '', gorsel: 'https://mehmetkuru.dev/api/v1/menu-gorsel/latte?b=b', fiyat: '50,00 ₺' },
  }));
  const y = await cagir('/menu/cinar-kafe?urun=42', ortam().env);
  const html = await y.text();
  assert.equal(cagrilar[0].adres, 'https://mehmetkuru-api.onrender.com/api/v1/menu/cinar-kafe/ozet?urun=42');
  assert.match(html, /<title>Latte — Çınar "Kafe" &amp; &lt;Bistro&gt;<\/title>/);
  assert.match(html, /<meta name="description" content="50,00 ₺ · Çınar &quot;Kafe&quot; &amp; &lt;Bistro&gt;">/);
  assert.match(html, /<meta property="og:type" content="product">/);
  assert.match(html, /<meta property="og:image" content="https:\/\/mehmetkuru\.dev\/api\/v1\/menu-gorsel\/latte\?b=b">/);
  assert.match(html, /<link rel="canonical" href="https:\/\/mehmetkuru\.dev\/menu\/cinar-kafe\?urun=42">/);
  // Sayısal olmayan ürün parametresi arka uca iletilmez.
  const c2 = arkaUc(json(OZET));
  await cagir('/menu/cinar-kafe?urun=1%3Bdrop', ortam().env);
  assert.equal(c2[0].adres, 'https://mehmetkuru-api.onrender.com/api/v1/menu/cinar-kafe/ozet');
});

test('dil ve indekslenebilir mağaza: lang/dir, og:locale, index', async () => {
  const cagrilar = arkaUc(json({ ...OZET, dil: 'ar', ad: 'مقهى', aciklama: '', indekslenebilir: true, gorsel: null }));
  const y = await cagir('/menu/cinar-kafe?dil=ar', ortam().env);
  const html = await y.text();
  assert.equal(cagrilar[0].adres, 'https://mehmetkuru-api.onrender.com/api/v1/menu/cinar-kafe/ozet?dil=ar');
  assert.match(html, /<html lang="ar" dir="rtl">/);
  assert.match(html, /<title>مقهى \| قائمة الطعام<\/title>/);
  assert.match(html, /<meta property="og:locale" content="ar_AR">/);
  assert.match(html, /<meta name="robots" content="index, follow">/);
  assert.match(html, /<meta name="twitter:card" content="summary">/);
  assert.doesNotMatch(html, /og:image/);
  assert.equal(y.headers.get('X-Robots-Tag'), null);
  assert.match(html, /<link rel="canonical" href="https:\/\/mehmetkuru\.dev\/menu\/cinar-kafe\?dil=ar">/);
});

test('katalog düzeni başlığı', async () => {
  arkaUc(json({ ...OZET, duzen: 'katalog', dil: 'en', ad: 'Shop' }));
  const html = await (await cagir('/menu/cinar-kafe', ortam().env)).text();
  assert.match(html, /<title>Shop \| Catalog<\/title>/);
});

test('menü yoksa 404, pasifse 410 (noindex, no-store); geçersiz slug arka uca gitmez', async () => {
  arkaUc(json({ detail: { kod: 'menu_yok' } }, 404));
  let y = await cagir('/menu/olmayan-menu', ortam().env);
  assert.equal(y.status, 404);
  assert.equal(y.headers.get('Cache-Control'), 'no-store');
  assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  let html = await y.text();
  assert.match(html, /<meta name="robots" content="noindex, nofollow">/);
  assert.doesNotMatch(html, /Ana sayfa içeriği|og:title/);

  arkaUc(json({ detail: { kod: 'menu_pasif' } }, 410));
  y = await cagir('/menu/kapali-kafe', ortam().env);
  assert.equal(y.status, 410);

  const cagrilar = arkaUc(json(OZET));
  y = await cagir('/menu/..%2Fadmin', ortam().env);
  assert.equal(cagrilar.length, 0);
  assert.equal(y.status, 404);
});

test('arka uç hatası, zaman aşımı ya da API_ORIGIN yoksa kabuk döner (noindex)', async () => {
  arkaUc(json({ detail: 'hata' }, 502));
  let y = await cagir('/menu/cinar-kafe', ortam().env);
  assert.equal(y.status, 200);
  let html = await y.text();
  assert.match(html, /<script type="module" src="\/assets\/index-abc\.js">/);
  assert.match(html, /<meta name="robots" content="noindex, nofollow">/);
  assert.equal(y.headers.get('Cache-Control'), 'no-store');

  globalThis.fetch = async () => {
    throw new Error('bağlantı reddedildi');
  };
  y = await cagir('/menu/cinar-kafe', ortam().env);
  assert.equal(y.status, 200);
  assert.match(await y.text(), /index-abc\.js/);

  // Zaman aşımı: arka uç hiç yanıt vermiyor → iptal sinyaliyle kabuk.
  globalThis.fetch = (adres, secenek) =>
    new Promise((_, reddet) => secenek.signal.addEventListener('abort', () => reddet(new Error('iptal'))));
  const bas = Date.now();
  y = await cagir('/menu/cinar-kafe', ortam().env);
  assert.equal(y.status, 200);
  assert.ok(Date.now() - bas >= ZAMAN_ASIMI_MS - 50);

  const cagrilar = arkaUc(json(OZET));
  y = await cagir('/menu/cinar-kafe', ortam({ API_ORIGIN: '' }).env);
  assert.equal(cagrilar.length, 0);
  assert.equal(y.status, 200);
  assert.match(await y.text(), /index-abc\.js/);
});

test('kabuk alınamazsa sade 502 sayfası; GET/HEAD dışı 405', async () => {
  arkaUc(json(OZET));
  let y = await cagir('/menu/cinar-kafe', { API_ORIGIN: 'https://api.ornek', ASSETS: { fetch: async () => new Response('', { status: 500 }) } });
  assert.equal(y.status, 502);
  assert.match(await y.text(), /yeniden deneyin/);
  y = await cagir('/menu/cinar-kafe', ortam().env, 'POST');
  assert.equal(y.status, 405);
  assert.equal(y.headers.get('Allow'), 'GET, HEAD');
});
