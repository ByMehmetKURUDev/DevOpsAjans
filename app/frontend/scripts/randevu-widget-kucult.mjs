/**
 * Faz 5R — gömülebilir randevu betiğini küçültür.
 *
 * Kaynak (okunur):  scripts/randevu-widget.kaynak.js
 * Çıktı (yayında):  public/randevu-widget.js  (~3 kB, gzip ~1,5 kB; ana uygulama paketine girmez)
 *
 * Kaynağı değiştirdikten sonra çalıştırın: `node scripts/randevu-widget-kucult.mjs`
 * (esbuild Vite ile birlikte kurulu; derleme zincirine bilerek eklenmedi —
 * çıktı depoda duruyor, Cloudflare derlemesi ek araç çalıştırmıyor).
 */
import fs from 'node:fs';
import { transform } from 'esbuild';

const kaynak = fs.readFileSync(new URL('./randevu-widget.kaynak.js', import.meta.url), 'utf8');
const { code } = await transform(kaynak, { minify: true, legalComments: 'none', target: 'es2017' });
const baslik = '/*! By Mehmet KURU Dev — randevu gömme betiği (kaynak: scripts/randevu-widget.kaynak.js) */\n';
const hedef = new URL('../public/randevu-widget.js', import.meta.url);
fs.writeFileSync(hedef, baslik + code);
console.log(`✓ public/randevu-widget.js: ${Buffer.byteLength(baslik + code)} bayt`);
