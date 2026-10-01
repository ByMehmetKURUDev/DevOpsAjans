/**
 * Faz 4G — Pages Function'larının arka uca "vekil imzası" eklemesi ve
 * kart/menü HTML'ine CSP başlığı.
 *
 * Çalıştırma: `node --test scripts/vekil-imzasi.test.mjs` (arka uç pytest'i de
 * `tests/backend/test_vekil_imzasi.py` üzerinden çağırıyor).
 *
 * Her Function için (`api/[[path]]`, `q/[kod]`, `kart/[slug]`, `menu/[slug]`):
 *   * `VEKIL_ANAHTARI` tanımlıysa `X-MK-Vekil-Anahtari` ekleniyor,
 *   * ziyaretçinin gönderdiği `X-MK-Vekil-Anahtari` / `X-MK-Istemci-IP` HER
 *     ZAMAN siliniyor; IP yalnız `CF-Connecting-IP`'den,
 *   * değişken yokken istek yine çalışıyor (başlık eklenmiyor).
 */
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { CSP_BASLIK_ADI, CSP_POLITIKASI, CSP_ZORUNLU, cspBasliklari } from '../functions/_ortak/csp.js';
import { IP_BASLIGI, VEKIL_BASLIGI, vekilAnahtari, vekilBasliklari } from '../functions/_ortak/vekil.js';

// menu Function'ı HTMLRewriter kullanıyor; Node'da yok — basit bir taklit yetiyor
// (bu testte yalnız başlıklara bakılıyor).
globalThis.HTMLRewriter ??= class {
  on() {
    return this;
  }
  transform(y) {
    return new Response(y.body, y);
  }
};

const { onRequest: api } = await import('../functions/api/[[path]].js');
const { onRequest: q } = await import('../functions/q/[kod].js');
const { onRequest: kart } = await import('../functions/kart/[slug].js');
const { onRequest: menu } = await import('../functions/menu/[slug].js');

const ANAHTAR = 'x'.repeat(48);
const gercekFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = gercekFetch;
});

/** fetch taklidi: her çağrının başlıklarını Headers olarak toplar. */
function taklit(yanit) {
  const cagrilar = [];
  globalThis.fetch = async (girdi, secenek = {}) => {
    const basliklar = girdi instanceof Request ? girdi.headers : new Headers(secenek.headers || {});
    cagrilar.push({ adres: String(girdi instanceof Request ? girdi.url : girdi), basliklar });
    return yanit();
  };
  return cagrilar;
}

const KABUK = '<!doctype html><html lang="tr"><head><title>Ana</title></head><body><div id="root"></div></body></html>';
const ASSETS = { fetch: async () => new Response(KABUK, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } }) };

const UYDURMA = {
  'CF-Connecting-IP': '198.51.100.7',
  [VEKIL_BASLIGI]: 'ziyaretcinin-uydurdugu',
  [IP_BASLIGI]: '203.0.113.99',
};

const FONKSIYONLAR = [
  {
    ad: 'api',
    cagir: (env, basliklar) =>
      api({ request: new Request('https://mehmetkuru.dev/api/v1/auth/me', { headers: basliklar }), env }),
    yanit: () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }),
  },
  {
    ad: 'q',
    cagir: (env, basliklar) =>
      q({ request: new Request('https://mehmetkuru.dev/q/Abc2345', { headers: basliklar }), env, params: { kod: 'Abc2345' } }),
    yanit: () => new Response(null, { status: 302, headers: { Location: 'https://ornek.com/' } }),
  },
  {
    ad: 'kart',
    cagir: (env, basliklar) =>
      kart({
        request: new Request('https://mehmetkuru.dev/kart/ayse-yilmaz', { headers: basliklar }),
        env: { ...env, ASSETS },
        params: { slug: 'ayse-yilmaz' },
      }),
    yanit: () => new Response(JSON.stringify({ durum: 'aktif', baslik: 'Ayşe', index: false }), { status: 200 }),
  },
  {
    ad: 'menu',
    cagir: (env, basliklar) =>
      menu({
        request: new Request('https://mehmetkuru.dev/menu/cinar-kafe', { headers: basliklar }),
        env: { ...env, ASSETS },
        params: { slug: 'cinar-kafe' },
      }),
    yanit: () => new Response(JSON.stringify({ ad: 'Çınar', dil: 'tr', duzen: 'menu' }), { status: 200 }),
  },
];

for (const f of FONKSIYONLAR) {
  test(`${f.ad}: anahtar tanımlıyken imza eklenir, ziyaretçinin uydurduğu başlıklar silinir`, async () => {
    const cagrilar = taklit(f.yanit);
    const y = await f.cagir({ API_ORIGIN: 'https://api.ornek', VEKIL_ANAHTARI: `  ${ANAHTAR}\n` }, UYDURMA);
    assert.ok(y.status < 500, `durum ${y.status}`);
    assert.equal(cagrilar.length, 1);
    const h = cagrilar[0].basliklar;
    assert.equal(h.get(VEKIL_BASLIGI), ANAHTAR);
    assert.equal(h.get(IP_BASLIGI), '198.51.100.7');
  });

  test(`${f.ad}: anahtar yokken istek çalışır, imza eklenmez, uydurulan başlıklar yine silinir`, async () => {
    const cagrilar = taklit(f.yanit);
    const y = await f.cagir({ API_ORIGIN: 'https://api.ornek' }, UYDURMA);
    assert.ok(y.status < 500, `durum ${y.status}`);
    const h = cagrilar[0].basliklar;
    assert.equal(h.get(VEKIL_BASLIGI), null);
    assert.equal(h.get(IP_BASLIGI), '198.51.100.7');
  });

  test(`${f.ad}: CF-Connecting-IP yoksa ziyaretçinin X-MK-Istemci-IP'si taşınmaz`, async () => {
    const cagrilar = taklit(f.yanit);
    await f.cagir({ API_ORIGIN: 'https://api.ornek', VEKIL_ANAHTARI: ANAHTAR }, { [IP_BASLIGI]: '203.0.113.99' });
    assert.equal(cagrilar[0].basliklar.get(IP_BASLIGI), null);
    assert.equal(cagrilar[0].basliklar.get(VEKIL_BASLIGI), ANAHTAR);
  });
}

test('kart ve menü HTML yanıtında sitenin CSP başlığı ve raporlama ucu var', async () => {
  for (const f of FONKSIYONLAR.filter((x) => x.ad === 'kart' || x.ad === 'menu')) {
    taklit(f.yanit);
    const y = await f.cagir({ API_ORIGIN: 'https://api.ornek' }, {});
    assert.equal(y.headers.get(CSP_BASLIK_ADI), CSP_POLITIKASI, f.ad);
    assert.match(y.headers.get('Reporting-Endpoints') || '', /csp="\/api\/v1\/csp-rapor"/, f.ad);
  }
  // Arka uç kapalıyken dönen kabukta da.
  globalThis.fetch = async () => {
    throw new Error('ag yok');
  };
  const y = await FONKSIYONLAR[2].cagir({ API_ORIGIN: 'https://api.ornek' }, {});
  assert.equal(y.headers.get(CSP_BASLIK_ADI), CSP_POLITIKASI);
});

test('CSP tek sabitle mod değiştirir; zorunlu yönergeler ve rapor ucu politikada', () => {
  assert.equal(CSP_BASLIK_ADI, CSP_ZORUNLU ? 'Content-Security-Policy' : 'Content-Security-Policy-Report-Only');
  for (const y of ["default-src 'self'", "object-src 'none'", "base-uri 'self'", "frame-ancestors 'self'", 'report-uri /api/v1/csp-rapor', 'report-to csp']) {
    assert.ok(CSP_POLITIKASI.includes(y), y);
  }
  assert.doesNotMatch(CSP_POLITIKASI, /script-src[^;]*'unsafe-inline'/);
  assert.doesNotMatch(CSP_POLITIKASI, /'unsafe-eval'/);
  assert.deepEqual(Object.keys(cspBasliklari()), [CSP_BASLIK_ADI, 'Reporting-Endpoints']);
});

test('yardımcı: boş/eksik ortamda güvenli', () => {
  assert.equal(vekilAnahtari(undefined), '');
  assert.equal(vekilAnahtari({ VEKIL_ANAHTARI: '   ' }), '');
  const h = vekilBasliklari(new Headers({ [VEKIL_BASLIGI]: 'x' }), new Request('https://a.b/'), {});
  assert.equal(h.get(VEKIL_BASLIGI), null);
  assert.equal(h.get(IP_BASLIGI), null);
});
