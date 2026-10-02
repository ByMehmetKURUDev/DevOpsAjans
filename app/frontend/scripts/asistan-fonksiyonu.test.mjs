/**
 * Faz 5A — `functions/asistan/[[yol]].js` (Cloudflare Pages Function) için birim testi.
 *
 * Çalıştırma: `node --test scripts/asistan-fonksiyonu.test.mjs` (arka uç pytest'i de
 * `tests/backend/test_ai_asistan_fonksiyon.py` üzerinden çağırıyor).
 *
 * Node'da `HTMLRewriter` yok: Function'ın kullandığı alt küme için küçük bir taklit var
 * (randevu/menü testlerindekiyle aynı). `fetch` ve `env.ASSETS` de taklit.
 * Doğrulananlar: her zaman noindex + no-store, ana sayfaya ait OG/canonical/hreflang/JSON-LD
 * kaldırılması, başlık ve dil/yön, normal sayfada SAMEORIGIN, gömülü pencerede
 * `frame-ancestors` izinli alan adlarından (boş → *), X-Frame-Options yok, başlık
 * enjeksiyonuna karşı alan adı süzgeci, 404/410, arka uç hatasında kabuk, POST 405.
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

const { onRequest, yolCoz, cerceveIzni, ZAMAN_ASIMI_MS } = await import('../functions/asistan/[[yol]].js');

const ANAHTAR = 'abcd2345efgh6789';
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
    ASSETS: { fetch: async () => new Response(KABUK, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8', etag: '"k"', 'x-frame-options': 'DENY' } }) },
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

const OZET = { ad: 'Destek "Asistanı" <b>', renk: '#0f766e', dil: 'tr', tam_sayfa: true, izinli_kokenler: [], avatar: null };

async function cagir(yol, env = ortam(), method = 'GET') {
  const url = new URL(`https://mehmetkuru.dev${yol}`);
  const parcalar = url.pathname.split('/').slice(2).filter(Boolean);
  return onRequest({ request: new Request(url, { method }), env, params: { yol: parcalar } });
}

const etiket = (html, desen) => (html.match(desen) || [])[1];
const fa = (y) => ((y.headers.get('content-security-policy') || '').match(/frame-ancestors ([^;]*)/) || [])[1];

test('yol çözümü: yalnız 16 karakterlik küçük harf/rakam anahtar', () => {
  assert.equal(yolCoz([ANAHTAR]), ANAHTAR);
  assert.equal(yolCoz(ANAHTAR), ANAHTAR);
  for (const p of [undefined, [], ['ABCD2345EFGH6789'], ['abc'], [ANAHTAR, 'x'], ['../../api/v1'], [ANAHTAR + 'a']]) assert.equal(yolCoz(p), null, String(p));
});

test('frame-ancestors değeri: boş → *, alan adları (şemasız) + alt alan adı, geçersizler (başlık enjeksiyonu) atlanır', () => {
  assert.equal(cerceveIzni([]), '*');
  assert.equal(cerceveIzni(null), '*');
  assert.equal(cerceveIzni(['Ornek.com', '*.magaza.ornek.net', 'ornek.com']), "'self' ornek.com *.ornek.com magaza.ornek.net *.magaza.ornek.net");
  assert.equal(cerceveIzni(["kotu.com; script-src *", 'a b.com', 'http://x.com', 'localhost', '1.2.3.4']), "'self'");
});

test('tam sayfa: başlık asistanın adı, her zaman noindex + no-store, SAMEORIGIN, ana sayfanın etiketleri kalkar', async () => {
  const cagrilar = arkaUc(json(OZET));
  const y = await cagir(`/asistan/${ANAHTAR}`);
  const html = await y.text();
  assert.deepEqual(cagrilar, [`https://api.ornek.dev/api/v1/asistan/${ANAHTAR}/ozet`]);
  assert.equal(y.status, 200);
  assert.match(html, /<title>Destek (?:"|&quot;)Asistanı(?:"|&quot;) &lt;b&gt; \| AI asistan<\/title>/);
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'noindex, nofollow');
  assert.equal((html.match(/<meta name="robots"/g) || []).length, 1);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('cache-control'), 'no-store');
  assert.equal(y.headers.get('x-frame-options'), 'SAMEORIGIN');
  assert.equal(fa(y), "'self'");
  assert.match(y.headers.get('content-security-policy'), /script-src 'self'/);
  for (const p of ['hreflang', 'application/ld+json', 'og:title', 'rel="canonical"', 'name="description"', 'Ana sayfa içeriği']) assert.ok(!html.includes(p), p);
  assert.match(html, /border:3px solid #0f766e/);
  assert.ok(!html.includes('<b>'), 'ad kaçışlı olmalı');
  assert.equal(y.headers.get('etag'), null);
});

test('gömülü: X-Frame-Options yok, frame-ancestors izinli alan adlarından; liste boşsa *', async () => {
  arkaUc(json({ ...OZET, izinli_kokenler: ['ornek.com'] }));
  let y = await cagir(`/asistan/${ANAHTAR}?gomulu=1`);
  await y.text();
  assert.equal(y.headers.get('x-frame-options'), null);
  assert.equal(fa(y), "'self' ornek.com *.ornek.com");
  assert.match(y.headers.get('content-security-policy'), /script-src 'self'/); // geri kalan politika aynı
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  arkaUc(json(OZET));
  y = await cagir(`/asistan/${ANAHTAR}?gomulu=1`);
  assert.equal(fa(y), '*');
  // Gömülü olmayan istekte izinli liste ne olursa olsun SAMEORIGIN.
  arkaUc(json({ ...OZET, izinli_kokenler: ['ornek.com'] }));
  y = await cagir(`/asistan/${ANAHTAR}`);
  assert.equal(y.headers.get('x-frame-options'), 'SAMEORIGIN');
  assert.equal(fa(y), "'self'");
});

test('dil: parametre > asistanın dili; Arapçada dir=rtl', async () => {
  arkaUc(json({ ...OZET, dil: 'ar', ad: 'مساعد' }));
  let html = await (await cagir(`/asistan/${ANAHTAR}`)).text();
  assert.match(html, /<html lang="ar" dir="rtl">/);
  assert.match(html, /<title>مساعد \| المساعد الذكي<\/title>/);
  arkaUc(json({ ...OZET, dil: 'ar' }));
  html = await (await cagir(`/asistan/${ANAHTAR}?dil=en`)).text();
  assert.match(html, /<html lang="en" dir="ltr">/);
});

test('404 / 410 ve geçersiz anahtar: arka uca gidilmez (geçersizse), noindex', async () => {
  arkaUc(json({ detail: { kod: 'asistan_yok' } }, 404));
  assert.equal((await cagir('/asistan/zzzz2345efgh6789')).status, 404);
  arkaUc(json({ detail: { kod: 'asistan_pasif' } }, 410));
  const y = await cagir(`/asistan/${ANAHTAR}?gomulu=1`);
  assert.equal(y.status, 410);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(fa(y), '*'); // gömülü pencerede "kullanılamıyor" yazısı görünsün
  const cagrilar = arkaUc(json(OZET));
  const g = await cagir('/asistan/GECERSIZ');
  assert.equal(g.status, 404);
  assert.equal(cagrilar.length, 0);
});

test('arka uç hatası ya da zaman aşımı: kabuk + noindex (200); kabuk yoksa 502; POST 405', async () => {
  arkaUc(json({}, 503));
  const y = await cagir(`/asistan/${ANAHTAR}?gomulu=1`);
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(fa(y), '*');
  globalThis.fetch = (adres, secenek) => new Promise((_, ret) => secenek.signal.addEventListener('abort', () => ret(new Error('abort'))));
  const bas = Date.now();
  const z = await cagir(`/asistan/${ANAHTAR}`);
  assert.equal(z.status, 200);
  assert.ok(Date.now() - bas < ZAMAN_ASIMI_MS + 1500);
  assert.equal((await cagir(`/asistan/${ANAHTAR}`, ortam(), 'POST')).status, 405);
  const k = await cagir(`/asistan/${ANAHTAR}`, { API_ORIGIN: 'https://api.ornek.dev' });
  assert.equal(k.status, 502);
  assert.equal(k.headers.get('x-robots-tag'), 'noindex, nofollow');
});
