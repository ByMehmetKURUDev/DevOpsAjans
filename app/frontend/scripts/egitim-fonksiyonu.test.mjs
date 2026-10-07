/**
 * Faz 6K — `functions/egitim/[[yol]].js` (Cloudflare Pages Function) birim testi. Çalıştırma:
 * `node --test scripts/egitim-fonksiyonu.test.mjs` (pytest `tests/backend/test_egitim_fonksiyon.py`
 * üzerinden de çağırıyor).
 *
 * Node'da `HTMLRewriter` yok: etkinlik testindeki küçük taklit. `fetch` ve `env.ASSETS` de taklit.
 * Doğrulananlar: kurs sayfasında OG/canonical/robots, noindex varsayılanı, indekslenebilir kursta
 * Course JSON-LD (kaçışlı, tek blok), öğrenci/yoklama/sertifika/okutucu sayfalarında arka uca
 * gidilmemesi + noindex + no-referrer, kamera izninin YALNIZ okutucuda açılması, kurum listesi,
 * 404/410, arka uç hatasında kabuk.
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

const { onRequest, yolCoz, IZINLER_KAMERA } = await import('../functions/egitim/[[yol]].js');

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

const OZET = {
  slug: 'python-baslangic', baslik: 'Python "başlangıç" <kursu>', aciklama: 'Sıfırdan Python.', dil: 'tr', renk: '#2563eb',
  indekslenebilir: false, adres_url: 'https://mehmetkuru.dev/egitim/python-baslangic', jsonld: null,
};
const JSONLD = {
  '@context': 'https://schema.org', '@type': 'Course', name: 'Python </script><script>alert(1)</script> kursu',
  description: 'Sıfırdan Python.', url: 'https://mehmetkuru.dev/egitim/python-baslangic', inLanguage: 'tr',
  provider: { '@type': 'Organization', name: 'By Mehmet KURU Dev' },
};

async function cagir(yol, env = ortam(), method = 'GET', basliklar = {}) {
  const url = new URL(`https://mehmetkuru.dev${yol}`);
  const parcalar = url.pathname.split('/').slice(2).filter(Boolean);
  return onRequest({ request: new Request(url, { method, headers: basliklar }), env, params: { yol: parcalar } });
}

const etiket = (html, desen) => (html.match(desen) || [])[1];
const JETON = `12-1-${'a'.repeat(32)}`;

test('yol çözümü: kurs, öğrenci, yoklama, sertifika, okutucu, kurum, ayrılmış adlar, geçersiz', () => {
  assert.deepEqual(yolCoz(['python-baslangic']), { tur: 'sayfa', slug: 'python-baslangic' });
  assert.deepEqual(yolCoz(['Python-Baslangic']), { tur: 'sayfa', slug: 'python-baslangic' });
  assert.deepEqual(yolCoz(['ogrenci', JETON]), { tur: 'ogrenci', gecerli: true });
  assert.deepEqual(yolCoz(['ogrenci', 'kotu']), { tur: 'ogrenci', gecerli: false });
  assert.deepEqual(yolCoz(['yoklama', JETON]), { tur: 'yoklama', gecerli: true });
  assert.deepEqual(yolCoz(['sertifika', 'ABCD-EFGH-JKLM']), { tur: 'sertifika', gecerli: true });
  assert.deepEqual(yolCoz(['sertifika', 'ABCD-EFGH-JKL0']), { tur: 'sertifika', gecerli: false });
  assert.deepEqual(yolCoz(['okut', '4', '17']), { tur: 'okut', gecerli: true });
  assert.deepEqual(yolCoz(['okut', '4', 'x']), { tur: 'okut', gecerli: false });
  assert.deepEqual(yolCoz(['kurum', 'akademi']), { tur: 'kurum', slug: 'akademi' });
  for (const kotu of [['ogrenci'], ['okut'], ['kurum'], ['sertifika'], ['ab'], ['-x'], [], undefined, ['a', 'b', 'c', 'd']]) {
    assert.deepEqual(yolCoz(kotu), { tur: 'yok' }, JSON.stringify(kotu));
  }
});

test('kurs sayfası: OG/canonical/robots; noindex varsayılan; JSON-LD yok; vekil imzası', async () => {
  const cagrilar = arkaUc(json(OZET));
  const y = await cagir('/egitim/python-baslangic', ortam({ VEKIL_ANAHTARI: 'gizli-vekil' }), 'GET', { 'CF-Connecting-IP': '198.51.100.7' });
  const html = await y.text();
  assert.equal(cagrilar.length, 1);
  assert.equal(cagrilar[0].adres, 'https://api.ornek.dev/api/v1/egitim/kurs/python-baslangic/ozet');
  assert.equal(cagrilar[0].basliklar.get('x-mk-vekil-anahtari'), 'gizli-vekil');
  assert.equal(y.status, 200);
  assert.equal(etiket(html, /<meta property="og:title" content="([^"]*)"/), 'Python &quot;başlangıç&quot; &lt;kursu&gt; | Kurs');
  assert.equal(etiket(html, /<link rel="canonical" href="([^"]*)"/), 'https://mehmetkuru.dev/egitim/python-baslangic');
  assert.equal(etiket(html, /<meta name="description" content="([^"]*)"/), 'Sıfırdan Python.');
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'noindex, nofollow');
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('x-frame-options'), 'SAMEORIGIN');
  assert.match(y.headers.get('permissions-policy'), /camera=\(\)/);
  assert.match(y.headers.get('content-security-policy') || '', /script-src 'self'/);
  assert.ok(!html.includes('hreflang'));
  assert.ok(!html.includes('application/ld+json'));
  assert.ok(!html.includes('Ana sayfa içeriği'));
});

test('indekslenebilir kurs: index + Course JSON-LD (kaçışlı, tek blok); Arapça lang/dir', async () => {
  arkaUc(json({ ...OZET, indekslenebilir: true, jsonld: JSONLD }));
  const y = await cagir('/egitim/python-baslangic');
  const html = await y.text();
  assert.equal(etiket(html, /<meta name="robots" content="([^"]*)"/), 'index, follow');
  assert.equal(y.headers.get('x-robots-tag'), null);
  const bloklar = html.match(/<script type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g) || [];
  assert.equal(bloklar.length, 1);
  const ic = bloklar[0].replace(/^<script[^>]*>/, '').replace(/<\/script>$/, '');
  assert.ok(!ic.includes('<'));
  const veri = JSON.parse(ic);
  assert.equal(veri['@type'], 'Course');
  assert.equal(veri.name, JSONLD.name);
  arkaUc(json({ ...OZET, dil: 'ar' }));
  const ar = await (await cagir('/egitim/python-baslangic')).text();
  assert.match(ar, /<html lang="ar" dir="rtl">/);
  assert.match(ar, /\| دورة<\/title>/);
});

test('öğrenci / yoklama / sertifika: arka uca gidilmez, noindex, no-referrer, kamera kapalı', async () => {
  const cagrilar = arkaUc(json(OZET));
  for (const [yol, baslik] of [[`/egitim/ogrenci/${JETON}`, 'Öğrenci sayfası'], [`/egitim/yoklama/${JETON}`, 'Yoklama'], ['/egitim/sertifika/ABCDEFGHJKLM', 'Sertifika doğrulama']]) {
    const y = await cagir(yol);
    const html = await y.text();
    assert.equal(y.status, 200, yol);
    assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
    assert.equal(y.headers.get('referrer-policy'), 'no-referrer');
    assert.match(y.headers.get('permissions-policy'), /camera=\(\)/);
    assert.match(html, new RegExp(`<title>${baslik} \\| By Mehmet KURU Dev</title>`));
    assert.ok(!html.includes('og:title'));
  }
  assert.equal(cagrilar.length, 0);
  assert.equal((await cagir('/egitim/ogrenci/kotu')).status, 404);
  assert.equal((await cagir('/egitim/sertifika/kotu')).status, 404);
});

test('panel okutucu: kamera izni YALNIZ burada, arka uca gidilmez, noindex', async () => {
  const cagrilar = arkaUc(json(OZET));
  const y = await cagir('/egitim/okut/4/17?mod=yonetici');
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('permissions-policy'), IZINLER_KAMERA);
  assert.match(IZINLER_KAMERA, /camera=\(self\)/);
  assert.equal(y.headers.get('referrer-policy'), 'no-referrer');
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal(cagrilar.length, 0);
  assert.equal((await cagir('/egitim/okut/4/x')).status, 404);
  assert.match((await cagir('/egitim/okut')).headers.get('permissions-policy'), /camera=\(\)/);
});

test('kurum listesi: başlık/canonical, her zaman noindex; 404', async () => {
  const cagrilar = arkaUc(json({ baslik: 'Akademi <Kurslar>', aciklama: '', kurum_adi: 'Akademi', items: [{}, {}] }));
  const y = await cagir('/egitim/kurum/akademi');
  const html = await y.text();
  assert.equal(cagrilar[0].adres, 'https://api.ornek.dev/api/v1/egitim/kurum/akademi');
  assert.match(html, /<title>Akademi &lt;Kurslar&gt; \| Kurslar<\/title>/);
  assert.equal(etiket(html, /<link rel="canonical" href="([^"]*)"/), 'https://mehmetkuru.dev/egitim/kurum/akademi');
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  arkaUc(json({ detail: { kod: 'liste_yok' } }, 404));
  assert.equal((await cagir('/egitim/kurum/yok-liste')).status, 404);
});

test('404 / 410, arka uç hatası: kabuk + noindex; kabuk yoksa sade sayfa; POST 405', async () => {
  arkaUc(json({ detail: { kod: 'kurs_yok' } }, 404));
  assert.equal((await cagir('/egitim/yok-boyle')).status, 404);
  arkaUc(json({ detail: { kod: 'kurs_pasif' } }, 410));
  assert.equal((await cagir('/egitim/kapali-kurs')).status, 410);
  const cagrilar = arkaUc(json(OZET));
  assert.equal((await cagir('/egitim/A_B')).status, 404);
  assert.equal((await cagir('/egitim/ogrenci')).status, 404);
  assert.equal(cagrilar.length, 0);
  arkaUc(json({}, 503));
  const y = await cagir('/egitim/python-baslangic');
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('x-robots-tag'), 'noindex, nofollow');
  assert.equal((await cagir('/egitim/python-baslangic', ortam(), 'POST')).status, 405);
  const s = await cagir('/egitim/python-baslangic', { API_ORIGIN: 'https://api.ornek.dev' });
  assert.equal(s.status, 502);
  assert.match(await s.text(), /Kurs sayfası şu an açılamadı/);
});
