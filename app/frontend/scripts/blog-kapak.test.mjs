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

import { buildSosyalSvg, buildSvg } from './generate-covers.mjs';

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

test('Google İşletme kapağı 1200x900, yazı ve logo ortadaki 900x900 alanda (Parti 19)', () => {
  const svg = buildSosyalSvg({ title: 'Müşteri Yolculuğu Analitiği (Customer Journey Analytics)', category: 'Veri ve Analitik' }, '4x3');
  assert.match(svg, /^<svg [^>]*width="1200" height="900"/);
  // Yazılar x=150'den başlıyor: 4:3 kırpmada sol 150 px gidebilir.
  const xler = [...svg.matchAll(/<text x="(\d+)"/g)].map((m) => Number(m[1]));
  assert.ok(xler.length >= 2 && xler.every((x) => x === 150), `metin x: ${xler}`);
  const logo = /<image x="150" y="730" width="(\d+)" height="84"/.exec(svg);
  assert.ok(logo, 'logo yok');
  assert.ok(150 + Number(logo[1]) <= 1050, `logo güvenli alanı aşıyor: ${logo[1]}`);
  // Başlık 17 karakterlik satırlara bölünüyor; en uzun satır güvenli alana sığmalı (DejaVu Bold ~0.62em).
  const satirlar = [...svg.matchAll(/font-size="(\d+)" font-weight="700" fill="#ffffff">([^<]+)</g)];
  for (const [, punto, metin] of satirlar) assert.ok(150 + metin.length * Number(punto) * 0.62 <= 1050, `taşan satır: ${metin}`);
});
