/**
 * Faz 4L — marka teması: Pages Function ilk boyama stili (`functions/_ortak/marka.js`) ve
 * kartvizit Function'ının (`functions/kart/[slug].js`) sunucu HTML'ine yazdığı `<style id="marka-temasi">`.
 *
 * Çalıştırma: `node --test scripts/marka-fonksiyonu.test.mjs` (arka uç pytest'i de
 * `tests/backend/test_marka.py` üzerinden çağırıyor). Node'da HTMLRewriter yok: kart Function'ı
 * metin yedeğine düşüyor (kart-fonksiyonu.test.mjs ile aynı yol).
 */
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { onRequest } from '../functions/kart/[slug].js';
import { ilkBoyamaStili, kartIlkBoyama, markaTemasi, markaUygulanir, sayfaIlkBoyama, yaziRengi } from '../functions/_ortak/marka.js';

const KABUK = `<!doctype html>
<html lang="tr" data-gorunum="modern">
  <head><meta charset="UTF-8"><title>Ana sayfa</title><meta name="description" content="Ana"></head>
  <body><div id="root"><main>Ana sayfa</main></div><script type="module" src="/assets/index-abc.js"></script></body>
</html>`;

const MARKA = {
  rozet: true,
  sayfa_ozel: false,
  tema: {
    ad: 'Ayşe Ajans', ana: '#0ea5e9', ana_yazi: '#111111', vurgu: '#b45309', vurgu_yazi: '#ffffff',
    zemin: 'koyu', kose: 'yuvarlak', yazi_tipi: 'sistem_serif', logo: null,
  },
};

const gercekFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = gercekFetch;
});

function ortam() {
  return {
    API_ORIGIN: 'https://api.ornek.dev',
    ASSETS: { fetch: async () => new Response(KABUK, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } }) },
  };
}

async function kartHtml(ozet) {
  globalThis.fetch = async () => new Response(JSON.stringify(ozet), { status: 200, headers: { 'content-type': 'application/json' } });
  const y = await onRequest({ request: new Request('https://mehmetkuru.dev/kart/ayse'), env: ortam(), params: { slug: 'ayse' } });
  return { y, html: await y.text() };
}

const OZET = {
  durum: 'aktif', slug: 'ayse', dil: 'tr', locale: 'tr_TR', index: false, kart_adresi: 'https://mehmetkuru.dev/kart/ayse',
  baslik: 'Ayşe', aciklama: 'x', gorsel: null,
  tema: { sablon: 'gece', renk: '#a855f7', yazi_tipi: 'jakarta', kose: 'yumusak' },
};

test("marka teması kart HTML'ine sunucuda yazılır (ilk boyama: zemin + --marka-* değişkenleri)", async () => {
  const { y, html } = await kartHtml({ ...OZET, marka: MARKA });
  assert.equal(y.status, 200);
  const stil = html.match(/<style id="marka-temasi">([^<]*)<\/style>/);
  assert.ok(stil, 'marka stili <head>de olmalı');
  assert.ok(html.indexOf('marka-temasi') < html.indexOf('</head>'));
  assert.match(stil[1], /--marka-ana:#0ea5e9/);
  assert.match(stil[1], /--marka-ana-yazi:#111111/);
  assert.match(stil[1], /--marka-zemin:#0b0b12/);
  assert.match(stil[1], /--marka-kose:28px/);
  assert.match(stil[1], /--marka-yazi-tipi:ui-serif/);
  assert.match(stil[1], /--marka-ilk-zemin:#0b0b12/);
  assert.match(stil[1], /html,html body\{background:#0b0b12 !important;color:#f4f4f7\}/);
  // CSP: betik eklenmedi, uygulama betiği yerinde.
  assert.equal((html.match(/<script/g) || []).length, 1);
  assert.match(y.headers.get('Content-Security-Policy') || '', /style-src 'self' 'unsafe-inline'/);
});

test('kartın kendi teması marka temasını ezer (sayfa_ozel): kartın zemini, marka değişkeni yok', async () => {
  const { html } = await kartHtml({
    ...OZET,
    tema: { sablon: 'doga', renk: '#16a34a', yazi_tipi: 'mono', kose: 'keskin' },
    marka: { ...MARKA, sayfa_ozel: true },
  });
  const stil = html.match(/<style id="marka-temasi">([^<]*)<\/style>/)[1];
  assert.match(stil, /--marka-ilk-zemin:#f3f1ea/);
  assert.doesNotMatch(stil, /--marka-ana/);
  // "canlı" şablonda zemin kartın kendi rengi.
  assert.match(kartIlkBoyama({ tema: { sablon: 'canli', renk: '#e11d48' } }), /--marka-ilk-zemin:#e11d48/);
});

test('marka yoksa kartın varsayılan zemini; yok/pasif kartta stil yazılmaz', async () => {
  const { html } = await kartHtml({ ...OZET, marka: { rozet: true, tema: null, sayfa_ozel: false } });
  assert.match(html, /--marka-ilk-zemin:#0b0714/);
  assert.doesNotMatch(html, /--marka-ana:/);
  const yok = await kartHtml({ durum: 'yok', index: false });
  assert.doesNotMatch(yok.html, /marka-temasi/);
});

test('bozuk ya da kötü niyetli değerler yazılmaz (stil enjeksiyonu yok)', () => {
  const kotu = { rozet: true, sayfa_ozel: false, tema: { ...MARKA.tema, ana: 'red;}</style><script>alert(1)</script>' } };
  assert.equal(markaTemasi(kotu), null);
  assert.equal(markaUygulanir(kotu), false);
  assert.equal(markaTemasi({ tema: { ...MARKA.tema, yazi_tipi: "x'}body{display:none" } }), null);
  assert.equal(markaTemasi({ tema: { ...MARKA.tema, zemin: 'mor' } }), null);
  assert.equal(ilkBoyamaStili({ zemin: 'url(javascript:1)', metin: '#fff' }), '');
  assert.doesNotMatch(kartIlkBoyama({ tema: { sablon: 'canli', renk: '</style>' } }), /<\/style><\/style>|script/);
  // Kötü ana_yazi varsayılana düşer.
  assert.equal(markaTemasi({ tema: { ...MARKA.tema, ana_yazi: 'kırmızı' } }).ana_yazi, '#ffffff');
});

test('menü/randevu: sayfanın kendi rengi öncelikli; zemin yalnız istenirse', () => {
  const m = sayfaIlkBoyama(MARKA, { sayfaRengi: '#16a34a' });
  assert.equal(m.ana, '#0ea5e9');
  assert.match(m.stil, /--marka-ana:#0ea5e9/);
  assert.doesNotMatch(m.stil, /html,html body/);
  const ozel = sayfaIlkBoyama({ ...MARKA, sayfa_ozel: true }, { sayfaRengi: '#16a34a', zeminUygula: true });
  assert.equal(ozel.ana, '#16a34a');
  assert.match(ozel.stil, /--marka-ana:#16a34a/);
  assert.match(ozel.stil, /--marka-ana-yazi:#111111/);
  assert.match(ozel.stil, /html,html body\{background:#0b0b12/);
  assert.deepEqual(sayfaIlkBoyama({ rozet: true, tema: null }), { stil: '', ana: null, tema: null });
  assert.equal(yaziRengi('#1d4ed8'), '#ffffff');
  assert.equal(yaziRengi('#facc15'), '#111111');
});
