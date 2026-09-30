/**
 * Site haritasındaki adresleri yayındaki biçime çevirir.
 *
 * `vite-plugin-sitemap` yolları üretilen HTML dosyalarından topluyor ve
 * eğik çizgisiz yazıyor (`/blog`). Cloudflare Pages ise bu isteği 308 ile
 * `/blog/` adresine yolluyor. Böyle kalırsa site haritası ve canonical,
 * doğrudan 200 dönmeyen bir adresi gösteriyor.
 *
 * Eklentinin bunun için bir seçeneği yok; derlemeden sonra burada
 * düzeltiliyor. `canonicalUrlPathFor` canonical etiketleriyle aynı
 * kaynaktan geldiği için ikisi hep aynı biçimde kalıyor.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { SITE_URL, canonicalUrlPathFor } from '../prerender/site.js';

const kok = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dosya = path.join(kok, 'dist', 'sitemap.xml');

if (!fs.existsSync(dosya)) {
  console.error('✗ sitemap.xml bulunamadı:', dosya);
  process.exit(1);
}

let degisen = 0;
const icerik = fs.readFileSync(dosya, 'utf8').replace(/<loc>\s*([^<\s]+)\s*<\/loc>/g, (tam, adres) => {
  if (!adres.startsWith(SITE_URL)) return tam;
  const yeni = SITE_URL + canonicalUrlPathFor(adres.slice(SITE_URL.length) || '/');
  if (yeni !== adres) degisen += 1;
  return tam.replace(adres, yeni);
});

fs.writeFileSync(dosya, icerik);
console.log(`✓ Site haritası: ${degisen} adres eğik çizgili biçime çevrildi.`);
