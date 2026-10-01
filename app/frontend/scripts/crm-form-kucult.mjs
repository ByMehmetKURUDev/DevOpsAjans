/**
 * Faz 3C — gömülebilir CRM formu betiğini küçültür.
 *
 * Kaynak (okunur):  scripts/crm-form.kaynak.js
 * Çıktı (yayında):  public/crm-form.js  (~4 kB, gzip ~2 kB; ana uygulama paketine girmez)
 *
 * Kaynağı değiştirdikten sonra çalıştırın: `node scripts/crm-form-kucult.mjs`
 * (esbuild Vite ile birlikte kurulu; derleme zincirine bilerek eklenmedi —
 * çıktı depoda duruyor, Cloudflare derlemesi ek araç çalıştırmıyor).
 */
import fs from 'node:fs';
import { transform } from 'esbuild';

const kaynak = fs.readFileSync(new URL('./crm-form.kaynak.js', import.meta.url), 'utf8');
const { code } = await transform(kaynak, { minify: true, legalComments: 'none', target: 'es2017' });
const baslik = '/*! By Mehmet KURU Dev — CRM aday formu (kaynak: scripts/crm-form.kaynak.js) */\n';
const hedef = new URL('../public/crm-form.js', import.meta.url);
fs.writeFileSync(hedef, baslik + code);
console.log(`✓ public/crm-form.js: ${Buffer.byteLength(baslik + code)} bayt`);
