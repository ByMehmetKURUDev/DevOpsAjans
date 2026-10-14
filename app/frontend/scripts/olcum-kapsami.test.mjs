/**
 * Parti 13 — ölçülmeyen (özel) yollar: `index.html` GA yükleyicisi ile
 * `src/lib/olcum.ts` (Pixel/Ads/dönüşüm) AYNI deseni kullanmalı.
 *
 * Çalıştırma: `node --test scripts/olcum-kapsami.test.mjs`
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';

const HTML = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const TS = fs.readFileSync(new URL('../src/lib/olcum.ts', import.meta.url), 'utf8');

function desen(metin, onEk) {
  const i = metin.indexOf(onEk);
  assert.ok(i >= 0, `${onEk} bulunamadı`);
  const bas = metin.indexOf('/^', i);
  const bit = metin.indexOf('/;', bas);
  return metin.slice(bas, bit + 1);
}

const htmlDeseni = desen(HTML, 'var OZEL =');
const tsDeseni = desen(TS, 'export const OZEL_YOL_DESENI =');

test('index.html ve olcum.ts aynı özel yol desenini kullanıyor', () => {
  assert.equal(htmlDeseni, tsDeseni);
});

test('paneller ve jetonlu bağlantılar özel; tanıtım sayfaları açık', () => {
  // eslint-disable-next-line no-new-func
  const re = new Function(`return ${tsDeseni}`)();
  const dilsiz = (y) => y.replace(/^\/(tr|en|de|ru|zh|hi|ar)(?=\/|$)/, '') || '/';
  for (const yol of ['/admin', '/admin/x', '/client', '/ode/abc', '/teklif/jeton', '/rapor-aylik/j', '/en/admin', '/kart/firma', '/q/kod']) {
    assert.ok(re.test(dilsiz(yol)), yol);
  }
  for (const yol of ['/', '/contact', '/services', '/blog/yazi', '/en', '/en/contact', '/moduller', '/kaynaklar', '/administrator-rehberi']) {
    assert.ok(!re.test(dilsiz(yol)), yol);
  }
});

test('GA yükleyicisi özel yolda yüklenmiyor ve geçişte bayrağı tazeliyor', () => {
  assert.match(HTML, /if \(ozelMi\(\)\) return;/);
  assert.match(HTML, /window\['ga-disable-' \+ GA_ID\] = ozelMi\(\);/);
  assert.match(HTML, /\['pushState', 'replaceState'\]/);
});
