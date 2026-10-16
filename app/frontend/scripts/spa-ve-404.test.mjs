// Parti 14: soft-404 kaldırma — `_redirects` üretimi ve 404.html.
// Çalıştırma: node --test scripts/spa-ve-404.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { BLOK_BASI, BLOK_SONU, blogYonlendirmeleri, kaynakYollari, sayfa404, spaKurallari, yonlendirmeleriYaz } from './spa-ve-404.mjs';
import { INTENTIONALLY_NOT_PRERENDERED } from './spa-yollari.mjs';

test('dil ağacının göreli rotası /:lang önekiyle yazılır', () => {
  assert.deepEqual(kaynakYollari('durum/:slug'), ['/:lang/durum/:slug']);
  assert.deepEqual(kaynakYollari('/teklif/:jeton'), ['/teklif/:jeton']);
  assert.deepEqual(kaynakYollari('/admin'), ['/admin', '/admin/']);
});

test('her istemci rotasının bir kuralı var, her yolu yakalayan kural yok', () => {
  const kurallar = spaKurallari();
  const kaynaklar = new Set(kurallar.map((s) => s.split(/\s+/)[0]));
  for (const rota of INTENTIONALLY_NOT_PRERENDERED) {
    for (const k of kaynakYollari(rota)) assert.ok(kaynaklar.has(k), k);
  }
  assert.ok(kaynaklar.has('/blog/:slug'), 'panelden yeni eklenen yazı derlemeye kadar istemcide çizilmeli');
  assert.ok(!kaynaklar.has('/*'));
  for (const s of kurallar) assert.match(s, /^\/\S*\s+\/\s+200$/);
  // Tekrarsız.
  assert.equal(kaynaklar.size, kurallar.length);
});

test('_redirects: eski joker kural silinir, blok bir kez eklenir (iki kez çalışsa da)', () => {
  const kaynak = '# yorum\n/eski  /yeni  301\n/*    /index.html   200\n';
  const bir = yonlendirmeleriYaz(kaynak, ['/admin  /  200']);
  const iki = yonlendirmeleriYaz(bir, ['/admin  /  200']);
  assert.equal(bir, iki);
  assert.ok(!/^\/\*\s/m.test(bir));
  assert.ok(bir.includes('/eski  /yeni  301'));
  assert.equal(bir.split(BLOK_BASI).length, 2);
  assert.ok(bir.trimEnd().endsWith(BLOK_SONU));
});

test('404.html: kök boş, ana sayfa SEO etiketleri yok, noindex var, satır içi betikler aynı', () => {
  const index = `<!doctype html><html lang="tr"><head>
    <meta charset="UTF-8" />
    <title>Ana sayfa | By Mehmet KURU Dev</title>
    <meta name="description" content="Ana sayfa açıklaması">
    <meta name="robots" content="index,follow">
    <meta property="og:title" content="Ana sayfa">
    <link rel="canonical" href="https://mehmetkuru.dev/">
    <link rel="alternate" hreflang="en" href="https://mehmetkuru.dev/en/">
    <script>console.log("kabuk")</script>
    <script type="module" crossorigin src="/assets/index-abc.js"></script>
    <script type="application/ld+json">{"@type":"Organization"}</script>
  </head><body><div id="root"><div><h1>Ana sayfa içeriği</h1></div></div>
  </body></html>`;
  const s = sayfa404(index);
  assert.ok(s.includes('<div id="root"></div>'));
  assert.ok(!s.includes('Ana sayfa içeriği'));
  assert.ok(s.includes('<title>Sayfa bulunamadı | By Mehmet KURU Dev</title>'));
  assert.ok(s.includes('<meta name="robots" content="noindex">'));
  assert.equal((s.match(/name="robots"/g) || []).length, 1);
  for (const yok of ['rel="canonical"', 'hreflang', 'og:title', 'application/ld+json', 'name="description"']) {
    assert.ok(!s.includes(yok), yok);
  }
  assert.ok(s.includes('<script>console.log("kabuk")</script>'), 'CSP özeti için satır içi betik birebir kalmalı');
  assert.ok(s.includes('/assets/index-abc.js'));
});

test('prerender edilmiş blog yazısının eğik çizgisiz adresi kendi sayfasına 301 ile gider', () => {
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'dist-'));
  for (const ad of ['seo-nedir', 'ga4-nedir']) {
    fs.mkdirSync(path.join(dist, 'blog', ad), { recursive: true });
    fs.writeFileSync(path.join(dist, 'blog', ad, 'index.html'), '<html></html>');
  }
  fs.mkdirSync(path.join(dist, 'blog', 'bos-klasor'));
  assert.deepEqual(blogYonlendirmeleri(dist), [
    '/blog/ga4-nedir  /blog/ga4-nedir/  301',
    '/blog/seo-nedir  /blog/seo-nedir/  301',
  ]);
  // Statik kurallar `/blog/:slug` yeniden yazmasından ÖNCE yazılmalı (ilk eşleşen kazanır).
  const metin = yonlendirmeleriYaz('', [...blogYonlendirmeleri(dist), ...spaKurallari()]);
  assert.ok(metin.indexOf('/blog/seo-nedir  /blog/seo-nedir/  301') < metin.indexOf('/blog/:slug  /  200'));
  assert.deepEqual(blogYonlendirmeleri(path.join(dist, 'yok')), []);
});
