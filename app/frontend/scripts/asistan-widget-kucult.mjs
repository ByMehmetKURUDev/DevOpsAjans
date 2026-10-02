/**
 * Faz 5A — gömülebilir AI asistan betiğini küçültür.
 *
 * Kaynak (okunur):  scripts/asistan-widget.kaynak.js
 * Çıktı (yayında):  public/asistan-widget.js  (gzip ~1,7 kB; ana uygulama paketine girmez)
 *
 * Kaynağı değiştirdikten sonra çalıştırın: `node scripts/asistan-widget-kucult.mjs`
 * (esbuild Vite ile birlikte kurulu; derleme zincirine bilerek eklenmedi —
 * çıktı depoda duruyor, Cloudflare derlemesi ek araç çalıştırmıyor).
 */
import fs from 'node:fs';
import zlib from 'node:zlib';
import { transform } from 'esbuild';

const kaynak = fs.readFileSync(new URL('./asistan-widget.kaynak.js', import.meta.url), 'utf8');
const { code } = await transform(kaynak, { minify: true, legalComments: 'none', target: 'es2017' });
const baslik = '/*! By Mehmet KURU Dev — AI asistan gömme betiği (kaynak: scripts/asistan-widget.kaynak.js) */\n';
const hedef = new URL('../public/asistan-widget.js', import.meta.url);
fs.writeFileSync(hedef, baslik + code);
const icerik = baslik + code;
console.log(`✓ public/asistan-widget.js: ${Buffer.byteLength(icerik)} bayt, gzip ${zlib.gzipSync(icerik).length} bayt`);
