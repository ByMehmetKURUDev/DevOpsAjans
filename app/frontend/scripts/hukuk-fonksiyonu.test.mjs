/**
 * Faz 6H — `functions/hukuk/[[yol]].js` (Cloudflare Pages Function) birim testi. Çalıştırma:
 * `node --test scripts/hukuk-fonksiyonu.test.mjs` (pytest `tests/backend/test_hukuk.py` üzerinden de çağırıyor).
 *
 * Node'da `HTMLRewriter` yok: eğitim/etkinlik testlerindeki küçük taklit. `fetch` ve `env.ASSETS` de taklit.
 * Doğrulananlar: müvekkil portalı HER ZAMAN noindex + X-Robots-Tag + no-referrer + no-store; arka uca
 * GİDİLMİYOR (jeton bir yetki belgesi; önizlemeye kişisel/dosya bilgisi yazılmaz, OG etiketi yok); kamera kapalı;
 * geçersiz jeton ve tanıtım sayfası denemesi 404 (reklam yasağı: herkese açık büro sayfası yok); POST 405.
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

const { onRequest, yolCoz, BASLIK } = await import('../functions/hukuk/[[yol]].js');

const KABUK =
  '<!doctype html><html lang="tr"><head><meta charset="UTF-8" />' +
  '<title>Web Geliştirme | By Mehmet KURU Dev</title>' +
  '<link rel="canonical" href="https://mehmetkuru.dev/">' +
  '<meta name="description" content="Ajans ana sayfası">' +
  '<meta property="og:title" content="Ajans"><meta name="robots" content="index, follow">' +
  '<script type="application/ld+json">{"@type":"Organization"}</script>' +
  '<script type="module" src="/assets/index-abc.js"></script>' +
  '</head><body><div id="root"><div>Ana sayfa içeriği</div></div></body></html>';

const gercekFetch = globalThis.fetch;
let arkaUcCagrisi = 0;
afterEach(() => {
  globalThis.fetch = gercekFetch;
});
function arkaUcYasak() {
  arkaUcCagrisi = 0;
  globalThis.fetch = async () => {
    arkaUcCagrisi += 1;
    throw new Error('arka uca gidilmemeli');
  };
}

function ortam(ek = {}) {
  return {
    API_ORIGIN: 'https://api.ornek.dev/',
    ASSETS: { fetch: async () => new Response(KABUK, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } }) },
    ...ek,
  };
}

async function cagir(yol, env = ortam(), method = 'GET') {
  const url = new URL(`https://mehmetkuru.dev${yol}`);
  const parcalar = url.pathname.split('/').slice(2).filter(Boolean);
  return onRequest({ request: new Request(url, { method }), env, params: { yol: parcalar } });
}

const JETON = `12-3-${'a'.repeat(32)}`;
const etiket = (html, desen) => (html.match(desen) || [])[1];

test('yol çözümü: yalnız /hukuk/muvekkil/<jeton>', () => {
  assert.deepEqual(yolCoz(['muvekkil', JETON]), { tur: 'muvekkil', gecerli: true });
  assert.deepEqual(yolCoz(['muvekkil', 'kotu']), { tur: 'muvekkil', gecerli: false });
  for (const kotu of [['muvekkil'], ['buro-adi'], ['tanitim', 'x'], [], undefined, ['muvekkil', JETON, 'x']]) {
    assert.deepEqual(yolCoz(kotu), { tur: 'yok' }, JSON.stringify(kotu));
  }
});

test('portal: noindex + X-Robots-Tag + no-referrer + no-store, arka uca gidilmez, OG/kanonik yok', async () => {
  arkaUcYasak();
  const y = await cagir(`/hukuk/muvekkil/${JETON}`);
  const html = await y.text();
  assert.equal(arkaUcCagrisi, 0);
  assert.equal(y.status, 200);
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'noindex, nofollow');
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('referrer-policy'), 'no-referrer');
  assert.equal(y.headers.get('cache-control'), 'no-store');
  assert.match(y.headers.get('permissions-policy'), /camera=\(\)/);
  assert.match(y.headers.get('content-security-policy') || '', /script-src 'self'/);
  assert.ok(!/og:title|twitter:title|application\/ld\+json|rel="canonical"/.test(html), 'paylaşım önizlemesi yok');
  assert.ok(html.includes(BASLIK.tr));
  assert.ok(html.includes('/assets/index-abc.js'), 'SPA paketi yükleniyor');
});

test('portal başlığı ?dil= ile (ar → rtl)', async () => {
  arkaUcYasak();
  const y = await cagir(`/hukuk/muvekkil/${JETON}?dil=ar`);
  const html = await y.text();
  assert.match(html, /<html[^>]*lang="ar"/);
  assert.match(html, /dir="rtl"/);
  assert.ok(html.includes(BASLIK.ar));
});

test('geçersiz jeton ve tanıtım sayfası denemesi 404 (noindex); POST 405', async () => {
  arkaUcYasak();
  for (const yol of ['/hukuk/muvekkil/kotu-jeton', '/hukuk/buro-adi', '/hukuk/tanitim/x']) {
    const y = await cagir(yol);
    assert.equal(y.status, 404, yol);
    assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow', yol);
  }
  const p = await cagir(`/hukuk/muvekkil/${JETON}`, ortam(), 'POST');
  assert.equal(p.status, 405);
  assert.equal(arkaUcCagrisi, 0);
});

test('kabuk alınamazsa sade sayfa (502, noindex)', async () => {
  arkaUcYasak();
  const y = await cagir(`/hukuk/muvekkil/${JETON}`, ortam({ ASSETS: undefined }));
  assert.equal(y.status, 502);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.match(await y.text(), /noindex, nofollow/);
});
