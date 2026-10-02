/**
 * Faz 5M — gömülebilir bülten abonelik formu betiğini küçültür.
 *
 * Kaynak (okunur):  scripts/bulten-form.kaynak.js
 * Çıktı (yayında):  public/bulten-form.js  (ana uygulama paketine girmez)
 *
 * Kaynağı değiştirdikten sonra çalıştırın: `node scripts/bulten-form-kucult.mjs`
 * (esbuild Vite ile birlikte kurulu; derleme zincirine bilerek eklenmedi — çıktı depoda
 * duruyor, Cloudflare derlemesi ek araç çalıştırmıyor). crm-form-kucult.mjs ile aynı düzen.
 */
import fs from 'node:fs';
import { transform } from 'esbuild';

const kaynak = fs.readFileSync(new URL('./bulten-form.kaynak.js', import.meta.url), 'utf8');
const { code } = await transform(kaynak, { minify: true, legalComments: 'none', target: 'es2017' });
const baslik = '/*! By Mehmet KURU Dev — bülten abonelik formu (kaynak: scripts/bulten-form.kaynak.js) */\n';
const hedef = new URL('../public/bulten-form.js', import.meta.url);
fs.writeFileSync(hedef, baslik + code);
console.log(`✓ public/bulten-form.js: ${Buffer.byteLength(baslik + code)} bayt`);
