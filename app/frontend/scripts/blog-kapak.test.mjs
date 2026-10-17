/**
 * Parti 17 — blog kapaklarının alt künyesi marka logosu.
 *
 * Eskiden kapakların altında düz "mehmetkuru.dev" yazısı vardı. Artık sitenin
 * üst barındaki marka logosu (PNG, SVG'ye gömülü) çiziliyor. Bu test logonun
 * kapakta olduğunu ve eski yazının geri gelmediğini denetliyor.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { buildSvg } from './generate-covers.mjs';

test('blog kapağının altında marka logosu var, "mehmetkuru.dev" yazısı yok', () => {
  const svg = buildSvg({ title: 'SEO Nedir? Google\'da Üst Sıralara Çıkmak İçin Rehber', category: 'SEO' });
  assert.match(svg, /<image x="72" y="497" width="\d+" height="76" href="data:image\/png;base64,[A-Za-z0-9+/=]+"\/>/);
  assert.doesNotMatch(svg, />mehmetkuru\.dev</);
  assert.doesNotMatch(svg, /<line x1="72" y1="520"/);
});

test('logo dosyası var ve genişliği oranına göre hesaplanıyor', () => {
  const veri = fs.readFileSync(new URL('./varliklar/marka-logosu-blog.png', import.meta.url));
  assert.equal(veri.subarray(1, 4).toString('latin1'), 'PNG');
  const w = veri.readUInt32BE(16);
  const h = veri.readUInt32BE(20);
  const svg = buildSvg({ title: 'Deneme', category: 'Website' });
  const genislik = Number(/<image x="72" y="497" width="(\d+)"/.exec(svg)[1]);
  assert.equal(genislik, Math.round((w * 76) / h));
  // Kapak 1200 px; logo metin alanının (x=72..820) içinde kalmalı.
  assert.ok(72 + genislik <= 820, `logo çok geniş: ${genislik}`);
});
