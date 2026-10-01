/**
 * Faz 4G — CSP tek kaynak (`functions/_ortak/csp.js`) → `_headers`.
 *
 * Çalıştırma: `node --test scripts/csp-basliklari.test.mjs` (pytest
 * `tests/backend/test_csp_rapor.py` de çağırıyor).
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';

import { CSP_BASLIK_ADI, CSP_POLITIKASI, CSP_ZORUNLU, RAPORLAMA_UCLARI } from '../functions/_ortak/csp.js';
import { ayristir, cspAyristir, cspYaz, satirIciHashler, YER_TUTUCU } from './guvenlik-basliklari.mjs';

const PUBLIC = fs.readFileSync(new URL('../public/_headers', import.meta.url), 'utf8');

test('public/_headers CSP yer tutucusu taşıyor; derleme onu csp.js politikasıyla dolduruyor', () => {
  assert.ok(PUBLIC.includes(`Content-Security-Policy: ${YER_TUTUCU}`));
  const cikti = cspYaz(PUBLIC);
  assert.ok(!cikti.split('\n').some((s) => !s.startsWith('#') && s.includes(YER_TUTUCU)));
  const { kurallar, hatalar } = ayristir(cikti);
  assert.deepEqual(hatalar, []);
  const genel = Object.fromEntries(kurallar.find((k) => k.yol === '/*').basliklar);
  assert.equal(genel[CSP_BASLIK_ADI.toLowerCase()], CSP_POLITIKASI);
  assert.equal(genel['reporting-endpoints'], RAPORLAMA_UCLARI);
  // Satır sınırı (Cloudflare: 2000 karakter).
  for (const satir of cikti.split('\n')) assert.ok(satir.length <= 2000);
});

test('kod deneme alanında sitenin CSP\'si ayrılıyor; çalıştırıcının kendi meta CSP\'si var', () => {
  const { kurallar } = ayristir(cspYaz(PUBLIC));
  for (const yol of ['/kod-deneme/', '/kod-deneme/index.html']) {
    const k = kurallar.find((x) => x.yol === yol);
    assert.ok(k, yol);
    assert.ok(k.basliklar.some(([a]) => a === `!${CSP_BASLIK_ADI.toLowerCase()}`), yol);
  }
  const html = fs.readFileSync(new URL('../public/kod-deneme/index.html', import.meta.url), 'utf8');
  assert.match(html, /<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:">/);
  // Yalnız üst pencereden gelen iletiyi işliyor.
  assert.match(html, /e\.source !== window\.parent/);
});

test('rapor moduna geri dönüş: başlık adları (ayırma satırları dahil) -Report-Only olur', () => {
  const cikti = cspYaz(PUBLIC, { ad: 'Content-Security-Policy-Report-Only' });
  assert.match(cikti, /\n {2}Content-Security-Policy-Report-Only: default-src 'self'/);
  assert.match(cikti, /\n {2}! Content-Security-Policy-Report-Only\n/);
  assert.doesNotMatch(cikti, /\n {2}Content-Security-Policy: /);
});

test('politika: satır içi betik yalnız özetle; eval yok; rapor ucu var', () => {
  const csp = cspAyristir(CSP_POLITIKASI);
  assert.ok(!csp['script-src'].includes("'unsafe-inline'"));
  assert.ok(!csp['script-src'].includes("'unsafe-eval'"));
  assert.deepEqual(csp['report-uri'], ['/api/v1/csp-rapor']);
  assert.deepEqual(csp['report-to'], ['csp']);
  assert.equal(CSP_BASLIK_ADI, CSP_ZORUNLU ? 'Content-Security-Policy' : 'Content-Security-Policy-Report-Only');
  // index.html'deki satır içi betiklerin özetleri politikada (kaynak index.html).
  const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const { betikler } = satirIciHashler(html);
  for (const h of betikler.keys()) assert.ok(csp['script-src'].includes(h), h);
});
