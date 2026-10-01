/**
 * Faz 4Q — `functions/q/[kod].js` (Cloudflare Pages Function) için küçük birim testi.
 *
 * Çalıştırma: `node --test scripts/q-fonksiyonu.test.mjs` (arka uç pytest'i de
 * `tests/backend/test_dinamik_qr_fonksiyon.py` üzerinden çağırıyor).
 *
 * `fetch` taklit ediliyor: Function'ın arka uca hangi adresi, hangi başlıklarla
 * ve `redirect: 'manual'` ile çağırdığı; 302'yi değiştirmeden (no-store)
 * döndürdüğü; dosya/HTML yanıtlarını geçirdiği; `API_ORIGIN` yokken anlamlı
 * hata verdiği; çerez/oturum başlıklarını iletmediği doğrulanıyor.
 */
import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';

import { onRequest } from '../functions/q/[kod].js';

const gercekFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = gercekFetch;
});

function istek(yol = '/q/Abc2345', basliklar = {}, cf = { country: 'TR' }, method = 'GET') {
  const r = new Request(`https://mehmetkuru.dev${yol}`, { method, headers: basliklar });
  Object.defineProperty(r, 'cf', { value: cf });
  return r;
}

function taklit(yanit) {
  const cagrilar = [];
  globalThis.fetch = async (adres, secenek) => {
    cagrilar.push({ adres: String(adres), secenek });
    return typeof yanit === 'function' ? yanit() : yanit;
  };
  return cagrilar;
}

test('başlıkları iletir, 302 yönlendirmeyi aynen ve no-store ile döndürür', async () => {
  const cagrilar = taklit(
    new Response(null, { status: 302, headers: { Location: 'https://ornek.com/kampanya?utm_source=qr' } })
  );
  const y = await onRequest({
    request: istek('/q/Abc2345', {
      'User-Agent': 'Mozilla/5.0 (iPhone)',
      Referer: 'https://www.instagram.com/',
      'Accept-Language': 'ar-SA,ar;q=0.9',
      'CF-Connecting-IP': '198.51.100.7',
      Cookie: 'oturum=gizli',
      Authorization: 'Bearer gizli',
    }),
    env: { API_ORIGIN: 'https://mehmetkuru-api.onrender.com/' },
    params: { kod: 'Abc2345' },
  });

  assert.equal(cagrilar.length, 1);
  const { adres, secenek } = cagrilar[0];
  assert.equal(adres, 'https://mehmetkuru-api.onrender.com/api/v1/q/Abc2345');
  assert.equal(secenek.redirect, 'manual');
  assert.equal(secenek.method, 'GET');
  const h = secenek.headers;
  assert.equal(h.get('X-MK-Istemci-IP'), '198.51.100.7');
  assert.equal(h.get('X-MK-Ulke'), 'TR');
  assert.equal(h.get('User-Agent'), 'Mozilla/5.0 (iPhone)');
  assert.equal(h.get('Referer'), 'https://www.instagram.com/');
  assert.equal(h.get('Accept-Language'), 'ar-SA,ar;q=0.9');
  assert.equal(h.get('X-Forwarded-Host'), 'mehmetkuru.dev');
  // Çerez ve oturum arka uca taşınmıyor (kısa adres herkese açık).
  assert.equal(h.get('Cookie'), null);
  assert.equal(h.get('Authorization'), null);

  assert.equal(y.status, 302);
  assert.equal(y.headers.get('Location'), 'https://ornek.com/kampanya?utm_source=qr');
  assert.equal(y.headers.get('Cache-Control'), 'no-store');
  assert.equal(y.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  assert.equal(y.headers.get('X-Content-Type-Options'), 'nosniff');
  assert.match(y.headers.get('Strict-Transport-Security'), /max-age=/);
});

test('vCard dosyasını ve 410 sayfasını olduğu gibi geçirir', async () => {
  taklit(
    new Response('BEGIN:VCARD\r\nVERSION:3.0\r\nEND:VCARD\r\n', {
      status: 200,
      headers: {
        'Content-Type': 'text/vcard; charset=utf-8',
        'Content-Disposition': 'attachment; filename="qr-Abc2345.vcf"',
        'Cache-Control': 'no-store',
      },
    })
  );
  let y = await onRequest({ request: istek(), env: { API_ORIGIN: 'https://api.ornek' }, params: { kod: 'Abc2345' } });
  assert.equal(y.status, 200);
  assert.equal(y.headers.get('Content-Type'), 'text/vcard; charset=utf-8');
  assert.match(y.headers.get('Content-Disposition'), /\.vcf/);
  assert.match(await y.text(), /^BEGIN:VCARD/);

  taklit(
    new Response('<!doctype html><title>Bu bağlantı şu an etkin değil</title>', {
      status: 410,
      headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
    })
  );
  y = await onRequest({ request: istek(), env: { API_ORIGIN: 'https://api.ornek' }, params: { kod: 'Abc2345' } });
  assert.equal(y.status, 410);
  assert.match(await y.text(), /etkin değil/);
  assert.equal(y.headers.get('Cache-Control'), 'no-store');
});

test('kodu adrese kodlayarak koyar; ülke yoksa başlık eklemez', async () => {
  const cagrilar = taklit(new Response('yok', { status: 404 }));
  await onRequest({
    request: istek('/q/x', {}, null),
    env: { API_ORIGIN: 'https://api.ornek' },
    params: { kod: '../admin?x=1' },
  });
  assert.equal(cagrilar[0].adres, 'https://api.ornek/api/v1/q/..%2Fadmin%3Fx%3D1');
  assert.equal(cagrilar[0].secenek.headers.get('X-MK-Ulke'), null);
  assert.equal(cagrilar[0].secenek.headers.get('X-MK-Istemci-IP'), null);
});

test('API_ORIGIN yoksa anlamlı 503, arka uca hiç gitmez', async () => {
  const cagrilar = taklit(new Response('olmamalı'));
  const y = await onRequest({ request: istek(), env: {}, params: { kod: 'Abc2345' } });
  assert.equal(cagrilar.length, 0);
  assert.equal(y.status, 503);
  assert.match(await y.text(), /API_ORIGIN/);
  assert.equal(y.headers.get('Cache-Control'), 'no-store');
});

test('arka uca ulaşılamazsa 502; GET/HEAD dışı 405', async () => {
  globalThis.fetch = async () => {
    throw new Error('bağlantı reddedildi');
  };
  let y = await onRequest({ request: istek(), env: { API_ORIGIN: 'https://api.ornek' }, params: { kod: 'Abc2345' } });
  assert.equal(y.status, 502);
  assert.match(await y.text(), /yeniden deneyin/);

  y = await onRequest({
    request: istek('/q/Abc2345', {}, { country: 'TR' }, 'POST'),
    env: { API_ORIGIN: 'https://api.ornek' },
    params: { kod: 'Abc2345' },
  });
  assert.equal(y.status, 405);
  assert.equal(y.headers.get('Allow'), 'GET, HEAD');
});

test('HEAD isteğini HEAD olarak iletir', async () => {
  const cagrilar = taklit(new Response(null, { status: 302, headers: { Location: 'https://ornek.com' } }));
  const y = await onRequest({
    request: istek('/q/Abc2345', {}, { country: 'DE' }, 'HEAD'),
    env: { API_ORIGIN: 'https://api.ornek' },
    params: { kod: 'Abc2345' },
  });
  assert.equal(cagrilar[0].secenek.method, 'HEAD');
  assert.equal(y.status, 302);
});
