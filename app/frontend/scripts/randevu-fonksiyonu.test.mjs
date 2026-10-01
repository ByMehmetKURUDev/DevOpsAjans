/**
 * Faz 5R — `functions/randevu/[[yol]].js` (Cloudflare Pages Function) için birim testi.
 *
 * Çalıştırma: `node --test scripts/randevu-fonksiyonu.test.mjs` (arka uç pytest'i de
 * `tests/backend/test_randevu_fonksiyon.py` üzerinden çağırıyor).
 *
 * Node'da `HTMLRewriter` yok: Function'ın kullandığı alt küme için küçük bir taklit var
 * (menü testindekiyle aynı). `fetch` ve `env.ASSETS` de taklit.
 * Doğrulananlar: sayfa ve etkinlik türü için OG/twitter/canonical/robots, ana sayfaya ait
 * hreflang/JSON-LD'nin kaldırılması, noindex varsayılanı, yönetim bağlantısında arka uca
 * gidilmemesi ve noindex, gömülü pencerede çerçeve izni, 404/410, arka uç hatasında kabuk.
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

const { onRequest, yolCoz, ZAMAN_ASIMI_MS } = await import('../functions/randevu/[[yol]].js');

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

function ortam() {
  return {
    API_ORIGIN: 'https://api.ornek.dev/',
    ASSETS: { fetch: async () => new Response(KABUK, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8', etag: '"k"' } }) },
  };
}

function arkaUc(yanit) {
  const cagrilar = [];
  globalThis.fetch = async (adres) => {
    cagrilar.push(String(adres));
    return typeof yanit === 'function' ? yanit(String(adres)) : yanit.clone();
  };
  return cagrilar;
}

const json = (veri, durum = 200) => new Response(JSON.stringify(veri), { status: durum, headers: { 'content-type': 'application/json' } });

const OZET = {
  slug: 'ayse-danismanlik', baslik: 'Ayşe "Danışmanlık" <Ofis>', aciklama: 'Size uygun saati seçin.', dil: 'tr',
  gorsel: 'https://mehmetkuru.dev/api/v1/randevu/gorsel/abc', renk: '#0f766e', indekslenebilir: false,
  adres_url: 'https://mehmetkuru.dev/randevu/ayse-danismanlik', tur: null,
};

async function cagir(yol, env = ortam(), method = 'GET') {
  const url = new URL(`https://mehmetkuru.dev${yol}`);
  const parcalar = url.pathname.split('/').slice(2).filter(Boolean);
  return onRequest({ request: new Request(url, { method }), env, params: { yol: parcalar } });
}

const etiket = (html, desen) => (html.match(desen) || [])[1];

test('yol çözümü: sayfa, etkinlik, yönetim, geçersiz', () => {
  assert.deepEqual(yolCoz(['ab']), { tur: 'yok' });
  assert.deepEqual(yolCoz(['-ayse']), { tur: 'yok' });
  assert.deepEqual(yolCoz(['ayse-d']), { tur: 'sayfa', slug: 'ayse-d' });
  assert.deepEqual(yolCoz(['Ayse-D', 'tanisma']), { tur: 'etkinlik', slug: 'ayse-d', etkinlik: 'tanisma' });
  assert.deepEqual(yolCoz(['yonet', '12-' + 'a'.repeat(32)]), { tur: 'yonet', gecerli: true });
  assert.deepEqual(yolCoz(['yonet', 'xyz']), { tur: 'yonet', gecerli: false });
  assert.deepEqual(yolCoz(undefined), { tur: 'yok' });
  assert.deepEqual(yolCoz(['a', 'b', 'c']), { tur: 'yok' });
});

test('sayfa: OG/twitter/canonical/robots yazılır, ana sayfanınkiler kalkar, noindex varsayılan', async () => {
  const cagrilar = arkaUc(json(OZET));
  const y = await cagir('/randevu/ayse-danismanlik');
  const html = await y.text();
  assert.deepEqual(cagrilar, ['https://api.ornek.dev/api/v1/randevu/ayse-danismanlik/ozet']);
  assert.equal(y.status, 200);
  assert.match(html, /<title>Ayşe (?:"|&quot;)Danışmanlık(?:"|&quot;) &lt;Ofis&gt; \| Randevu al<\/title>/);
  assert.equal(etiket(html, /<meta property="og:title" content="([^"]*)"/), 'Ayşe &quot;Danışmanlık&quot; &lt;Ofis&gt; | Randevu al');
  assert.equal(etiket(html, /<link rel="canonical" href="([^"]*)"/), 'https://mehmetkuru.dev/randevu/ayse-danismanlik');
  assert.equal(etiket(html, /<meta property="og:image" content="([^"]*)"/), 'https://mehmetkuru.dev/api/v1/randevu/gorsel/abc');
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'noindex, nofollow');
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('x-frame-options'), 'SAMEORIGIN');
  assert.ok(!html.includes('hreflang'), 'hreflang kaldırılmalı');
  assert.ok(!html.includes('application/ld+json'), 'JSON-LD kaldırılmalı');
  assert.ok(!html.includes('Ana sayfa içeriği'), 'iskelet konmalı');
  assert.equal((html.match(/<meta name="robots"/g) || []).length, 1);
  assert.equal(y.headers.get('etag'), null);
});

test('etkinlik türü: başlık ve canonical türe göre; dil parametresi; indekslenebilir sayfa', async () => {
  const cagrilar = arkaUc(json({ ...OZET, indekslenebilir: true, tur: { slug: 'tanisma', ad: 'Tanışma', aciklama: '', sure_dk: 30, adres_url: 'https://mehmetkuru.dev/randevu/ayse-danismanlik/tanisma' } }));
  const y = await cagir('/randevu/ayse-danismanlik/tanisma?dil=en');
  const html = await y.text();
  assert.deepEqual(cagrilar, ['https://api.ornek.dev/api/v1/randevu/ayse-danismanlik/ozet?tur=tanisma']);
  assert.match(html, /<html lang="en" dir="ltr">/);
  assert.match(html, /<meta property="og:description" content="Tanışma · 30 min · /);
  assert.equal(etiket(html, /<link rel="canonical" href="([^"]*)"/), 'https://mehmetkuru.dev/randevu/ayse-danismanlik/tanisma');
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'index, follow');
  assert.equal(y.headers.get('x-robots-tag'), null);
});

test('Arapça: dir=rtl', async () => {
  arkaUc(json({ ...OZET, dil: 'ar' }));
  const html = await (await cagir('/randevu/ayse-danismanlik')).text();
  assert.match(html, /<html lang="ar" dir="rtl">/);
  assert.match(html, /<meta property="og:locale" content="ar_AR">/);
});

test('gömülü pencere: çerçeve izni (frame-ancestors *), X-Frame-Options yok, her zaman noindex', async () => {
  arkaUc(json({ ...OZET, indekslenebilir: true }));
  const y = await cagir('/randevu/ayse-danismanlik?gomulu=1');
  await y.text();
  assert.equal(y.headers.get('x-frame-options'), null);
  const csp = y.headers.get('content-security-policy') || '';
  assert.match(csp, /frame-ancestors \*(;|$)/);
  assert.match(csp, /script-src 'self'/); // sitenin politikası korunuyor, yalnız çerçeve izni gevşiyor
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
});

test('yönetim bağlantısı: arka uca gidilmez, kişisel bilgi yok, noindex', async () => {
  const cagrilar = arkaUc(json(OZET));
  const y = await cagir('/randevu/yonet/12-' + 'b'.repeat(32));
  const html = await y.text();
  assert.equal(cagrilar.length, 0);
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.match(html, /<title>Randevunuz \| By Mehmet KURU Dev<\/title>/);
  assert.ok(!html.includes('og:title'));
  const g = await cagir('/randevu/yonet/gecersiz');
  assert.equal(g.status, 404);
});

test('404 / 410 durumları ve geçersiz yol', async () => {
  arkaUc(json({ detail: { kod: 'sayfa_yok' } }, 404));
  assert.equal((await cagir('/randevu/yok-boyle')).status, 404);
  arkaUc(json({ detail: { kod: 'sayfa_pasif' } }, 410));
  const y = await cagir('/randevu/kapali-sayfa');
  assert.equal(y.status, 410);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  const cagrilar = arkaUc(json(OZET));
  assert.equal((await cagir('/randevu/A_B')).status, 404);
  assert.equal(cagrilar.length, 0);
});

test('arka uç hatası ya da zaman aşımı: kabuk + noindex (200), POST 405', async () => {
  arkaUc(json({}, 503));
  const y = await cagir('/randevu/ayse-danismanlik');
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  globalThis.fetch = (adres, secenek) =>
    new Promise((_, ret) => secenek.signal.addEventListener('abort', () => ret(new Error('abort'))));
  const bas = Date.now();
  const z = await cagir('/randevu/ayse-danismanlik');
  assert.equal(z.status, 200);
  assert.ok(Date.now() - bas < ZAMAN_ASIMI_MS + 1500);
  assert.equal((await cagir('/randevu/ayse-danismanlik', ortam(), 'POST')).status, 405);
});
