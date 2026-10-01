/**
 * Faz 4K — `functions/kart/[slug].js` (Cloudflare Pages Function) için birim testi.
 *
 * Çalıştırma: `node --test scripts/kart-fonksiyonu.test.mjs` (arka uç pytest'i de
 * `tests/backend/test_kartvizit_fonksiyon.py` üzerinden çağırıyor).
 *
 * `fetch` (arka uç özeti) ve `env.ASSETS.fetch` (SPA kabuğu) taklit ediliyor.
 * Node'da HTMLRewriter yok: Function aynı kuralları metin üzerinde uygulayan
 * yedek yola düşüyor — OG etiketleri orada doğrulanıyor. Üretim yolu
 * (HTMLRewriter) sahte bir HTMLRewriter ile ayrıca deneniyor: hangi seçicilerin
 * kaydedildiği ve işleyicilerin öğeye ne yaptığı.
 */
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { KALDIRILANLAR, etiketler, htmlRewriterIle, onRequest } from '../functions/kart/[slug].js';

const KABUK = `<!doctype html>
<html lang="tr" data-gorunum="modern">
  <head>
    <meta charset="UTF-8">
    <title>Web Geliştirme ve Dijital Pazarlama | By Mehmet KURU Dev</title>
    <link rel="canonical" href="https://mehmetkuru.dev/">
    <meta name="description" content="Ana sayfa açıklaması">
    <meta property="og:title" content="Ana sayfa">
    <meta property="og:url" content="https://mehmetkuru.dev/">
    <meta property="og:image" content="https://mehmetkuru.dev/assets/og-cover.webp">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Ana sayfa">
    <link rel="alternate" hreflang="tr" href="https://mehmetkuru.dev/">
    <link rel="alternate" hreflang="en" href="https://mehmetkuru.dev/en/">
    <script type="module" src="/assets/index-abc.js"></script>
    <script type="application/ld+json">{"@type":"FAQPage"}</script>
  </head>
  <body>
    <div id="root"><div class="min-h-screen"><header>Ana sayfa menüsü</header><main><h1>Ana sayfa başlığı</h1></main></div></div>
  </body>
</html>`;

const gercekFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = gercekFetch;
  delete globalThis.HTMLRewriter;
});

function ortam(ek = {}) {
  const istenen = [];
  return {
    istenen,
    env: {
      API_ORIGIN: 'https://mehmetkuru-api.onrender.com/',
      ASSETS: {
        fetch: async (istek) => {
          istenen.push(String(istek.url ?? istek));
          return new Response(KABUK, {
            status: 200,
            headers: { 'content-type': 'text/html; charset=utf-8', etag: '"kabuk"', 'content-length': String(KABUK.length) },
          });
        },
      },
      ...ek,
    },
  };
}

function istek(yol = '/kart/ayse-yilmaz', basliklar = {}, method = 'GET') {
  return new Request(`https://mehmetkuru.dev${yol}`, { method, headers: basliklar });
}

function taklit(yanit) {
  const cagrilar = [];
  globalThis.fetch = async (adres, secenek) => {
    cagrilar.push({ adres: String(adres), secenek });
    if (yanit instanceof Error) throw yanit;
    return typeof yanit === 'function' ? yanit() : yanit;
  };
  return cagrilar;
}

const json = (veri, status = 200) =>
  new Response(JSON.stringify(veri), { status, headers: { 'content-type': 'application/json' } });

const AKTIF = {
  durum: 'aktif',
  slug: 'ayse-yilmaz',
  dil: 'tr',
  locale: 'tr_TR',
  index: false,
  kart_adresi: 'https://mehmetkuru.dev/kart/ayse-yilmaz',
  baslik: 'Ayşe Yılmaz — Kurucu · Örnek Ajans',
  aciklama: 'Web ve mobil ürünler geliştiriyoruz.',
  gorsel: 'https://mehmetkuru.dev/api/v1/kart/gorsel/AbCdEf123.jpg',
  gorsel_genislik: 640,
  gorsel_yukseklik: 640,
  gorsel_alt: 'Ayşe Yılmaz',
};

test('etkin kartta OG / twitter / canonical / robots yazılır, ana sayfa etiketleri kalkar', async () => {
  const cagrilar = taklit(json(AKTIF));
  const o = ortam();
  const y = await onRequest({
    request: istek('/kart/ayse-yilmaz', { Cookie: 'oturum=gizli', Authorization: 'Bearer gizli', 'Accept-Language': 'tr' }),
    env: o.env,
    params: { slug: 'ayse-yilmaz' },
  });
  assert.equal(cagrilar.length, 1);
  assert.equal(cagrilar[0].adres, 'https://mehmetkuru-api.onrender.com/api/v1/kart/ayse-yilmaz/ozet');
  const h = cagrilar[0].secenek.headers;
  assert.equal(h.get('Cookie'), null);
  assert.equal(h.get('Authorization'), null);
  assert.equal(o.istenen[0], 'https://mehmetkuru.dev/');

  assert.equal(y.status, 200);
  assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('Cache-Control'), 'no-cache');
  assert.equal(y.headers.get('etag'), null);
  assert.equal(y.headers.get('content-length'), null);
  assert.match(y.headers.get('Strict-Transport-Security'), /max-age=/);
  const html = await y.text();
  assert.match(html, /<title>Ayşe Yılmaz — Kurucu · Örnek Ajans<\/title>/);
  assert.match(html, /<meta property="og:title" content="Ayşe Yılmaz — Kurucu · Örnek Ajans">/);
  assert.match(html, /<meta property="og:description" content="Web ve mobil ürünler geliştiriyoruz.">/);
  assert.match(html, /<meta property="og:type" content="profile">/);
  assert.match(html, /<meta property="og:url" content="https:\/\/mehmetkuru.dev\/kart\/ayse-yilmaz">/);
  assert.match(html, /<meta property="og:image" content="https:\/\/mehmetkuru.dev\/api\/v1\/kart\/gorsel\/AbCdEf123.jpg">/);
  assert.match(html, /<meta property="og:image:width" content="640">/);
  assert.match(html, /<meta name="twitter:card" content="summary">/);
  assert.match(html, /<meta name="twitter:image" content="https:\/\/mehmetkuru.dev\/api\/v1\/kart\/gorsel\/AbCdEf123.jpg">/);
  assert.match(html, /<link rel="canonical" href="https:\/\/mehmetkuru.dev\/kart\/ayse-yilmaz">/);
  assert.match(html, /<meta name="robots" content="noindex, nofollow">/);
  assert.match(html, /<meta name="description" content="Web ve mobil ürünler geliştiriyoruz.">/);
  // Ana sayfanın etiketleri, hreflang ve yapısal verisi yok; ön çizim boşaltılmış.
  assert.doesNotMatch(html, /Ana sayfa açıklaması|og-cover\.webp|summary_large_image|hreflang|ld\+json|FAQPage/);
  assert.doesNotMatch(html, /Ana sayfa başlığı|Ana sayfa menüsü/);
  assert.match(html, /<div id="root"><\/div>/);
  assert.equal((html.match(/<meta property="og:title"/g) || []).length, 1);
  assert.equal((html.match(/rel="canonical"/g) || []).length, 1);
  // Uygulama betiği yerinde (SPA açılabilsin).
  assert.match(html, /<script type="module" src="\/assets\/index-abc.js"><\/script>/);
});

test('arama motoru izni açıksa index, follow; Arapça kartta lang/dir', async () => {
  taklit(json({ ...AKTIF, index: true, dil: 'ar', locale: 'ar_AR' }));
  const y = await onRequest({ request: istek(), env: ortam().env, params: { slug: 'ayse-yilmaz' } });
  assert.equal(y.headers.get('X-Robots-Tag'), 'index, follow');
  const html = await y.text();
  assert.match(html, /<meta name="robots" content="index, follow">/);
  assert.match(html, /<html data-gorunum="modern" lang="ar" dir="rtl">/);
  assert.match(html, /<meta property="og:locale" content="ar_AR">/);
});

test('parolalı kartta önizlemede kişisel bilgi ve görsel yok, noindex', async () => {
  // Arka uç zaten kişisel bilgi vermiyor; Function da görseli kesin olarak yazmıyor.
  taklit(json({
    durum: 'kilitli',
    slug: 'gizli-kart',
    dil: 'tr',
    index: true,
    kart_adresi: 'https://mehmetkuru.dev/kart/gizli-kart',
    baslik: 'Korumalı dijital kartvizit',
    aciklama: 'Bu kartvizit parola ile korunuyor.',
    gorsel: 'https://mehmetkuru.dev/api/v1/kart/gorsel/SIZINTI.jpg',
  }));
  const y = await onRequest({ request: istek('/kart/gizli-kart'), env: ortam().env, params: { slug: 'gizli-kart' } });
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  const html = await y.text();
  assert.match(html, /<title>Korumalı dijital kartvizit<\/title>/);
  assert.match(html, /<meta property="og:title" content="Korumalı dijital kartvizit">/);
  assert.doesNotMatch(html, /og:image|twitter:image|SIZINTI/);
  assert.match(html, /<meta name="robots" content="noindex, nofollow">/);
});

test('arka uç hata verirse / zaman aşımında / API_ORIGIN yoksa kabuk olduğu gibi döner', async () => {
  for (const yanit of [new Error('ag yok'), json({ detail: 'x' }, 502), new Response('<html>bozuk', { status: 200 })]) {
    taklit(yanit);
    const y = await onRequest({ request: istek(), env: ortam().env, params: { slug: 'ayse-yilmaz' } });
    assert.equal(y.status, 200);
    assert.equal(await y.text(), KABUK);
  }
  const cagrilar = taklit(json(AKTIF));
  const y = await onRequest({ request: istek(), env: ortam({ API_ORIGIN: '' }).env, params: { slug: 'ayse-yilmaz' } });
  assert.equal(await y.text(), KABUK);
  assert.equal(cagrilar.length, 0);
  // Geçersiz adres arka uca hiç sorulmuyor.
  const y2 = await onRequest({ request: istek('/kart/%3Cx%3E'), env: ortam().env, params: { slug: '<x>' } });
  assert.equal(await y2.text(), KABUK);
  assert.equal(cagrilar.length, 0);
});

test('eski slug 301, bilinmeyen 404, pasif 410 (noindex)', async () => {
  taklit(json({ durum: 'yonlendir', yonlendir: 'yeni-slug', index: false }));
  let y = await onRequest({ request: istek('/kart/eski-slug?ref=qr'), env: ortam().env, params: { slug: 'eski-slug' } });
  assert.equal(y.status, 301);
  assert.equal(y.headers.get('Location'), '/kart/yeni-slug?ref=qr');
  assert.equal(y.headers.get('Cache-Control'), 'no-store');
  taklit(json({ durum: 'yonlendir', yonlendir: 'https://kotu.example/x', index: false }));
  y = await onRequest({ request: istek('/kart/eski-slug'), env: ortam().env, params: { slug: 'eski-slug' } });
  assert.notEqual(y.status, 301);
  for (const [durum, kod] of [['yok', 404], ['pasif', 410]]) {
    taklit(json({ durum, index: false }));
    y = await onRequest({ request: istek('/kart/olmayan-kart'), env: ortam().env, params: { slug: 'olmayan-kart' } });
    assert.equal(y.status, kod);
    assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
    const html = await y.text();
    assert.match(html, /<meta name="robots" content="noindex, nofollow">/);
    assert.doesNotMatch(html, /og:title/);
  }
});

test('HTML kaçışı: başlıktaki işaretler etiket kıramaz', async () => {
  taklit(json({ ...AKTIF, baslik: '"><script>alert(1)</script>', aciklama: "O'Neil & <b>" }));
  const y = await onRequest({ request: istek(), env: ortam().env, params: { slug: 'ayse-yilmaz' } });
  const html = await y.text();
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /content="&quot;&gt;&lt;script&gt;alert\(1\)&lt;\/script&gt;"/);
  assert.match(html, /content="O&#39;Neil &amp; &lt;b&gt;"/);
  // javascript: görsel adresi yazılmıyor.
  const e = etiketler({ ...AKTIF, gorsel: 'javascript:alert(1)' }, 'https://mehmetkuru.dev/kart/x');
  assert.doesNotMatch(e.eklenecek, /og:image/);
});

test('HEAD isteği gövdesiz, aynı başlıklarla', async () => {
  taklit(json(AKTIF));
  const y = await onRequest({ request: istek('/kart/ayse-yilmaz', {}, 'HEAD'), env: ortam().env, params: { slug: 'ayse-yilmaz' } });
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  assert.equal(await y.text(), '');
});

test('üretim yolu: HTMLRewriter seçicileri ve işleyicileri', async () => {
  const kayit = [];
  class SahteRewriter {
    on(secici, isleyici) {
      kayit.push({ secici, isleyici });
      return this;
    }
    transform(yanit) {
      return yanit;
    }
  }
  globalThis.HTMLRewriter = SahteRewriter;
  const e = etiketler(AKTIF, 'https://mehmetkuru.dev/kart/ayse-yilmaz');
  htmlRewriterIle(new Response('x'), e);
  const seciciler = kayit.map((k) => k.secici);
  for (const s of [...KALDIRILANLAR, 'html', 'title', 'head', '#root']) assert.ok(seciciler.includes(s), s);

  const oge = () => {
    const izler = [];
    return {
      izler,
      remove: () => izler.push(['remove']),
      setAttribute: (a, d) => izler.push(['attr', a, d]),
      setInnerContent: (m, s) => izler.push(['inner', m, s]),
      append: (m, s) => izler.push(['append', m, s]),
    };
  };
  const calistir = (secici) => {
    const o = oge();
    kayit.find((k) => k.secici === secici).isleyici.element(o);
    return o.izler;
  };
  assert.deepEqual(calistir('meta[property^="og:"]'), [['remove']]);
  assert.deepEqual(calistir('script[type="application/ld+json"]'), [['remove']]);
  assert.deepEqual(calistir('title'), [['inner', AKTIF.baslik, undefined]]);
  assert.deepEqual(calistir('#root'), [['inner', '', undefined]]);
  assert.deepEqual(calistir('html'), [['attr', 'lang', 'tr'], ['attr', 'dir', 'ltr']]);
  const head = calistir('head');
  assert.equal(head[0][0], 'append');
  assert.deepEqual(head[0][2], { html: true });
  assert.match(head[0][1], /og:title/);

  // onRequest de HTMLRewriter varken onu kullanıyor (yedek metin yolu çalışmıyor).
  taklit(json(AKTIF));
  kayit.length = 0;
  const y = await onRequest({ request: istek(), env: ortam().env, params: { slug: 'ayse-yilmaz' } });
  assert.ok(kayit.length > 5);
  assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
});
