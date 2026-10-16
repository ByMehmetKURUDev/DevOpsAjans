/**
 * Paylaşım görsellerinin JPG eşleri — derleme verisi (`virtual:paylasim-jpg`).
 *
 * `prerender/app.js` tarayıcı paketinin içinde derleniyor, dosya sistemine
 * erişemiyor. Hangi kapağın JPG eşi olduğunu bu eklenti derlemede (Node'da)
 * `public/` klasöründen okuyup sanal modül olarak veriyor; og:image yalnız
 * JPG'si gerçekten olan kapaklarda JPG'ye çevriliyor, olmayanda WebP kalıyor.
 *
 * JPG'leri `npm run covers` (scripts/generate-covers.mjs) üretiyor.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SANAL_KIMLIK = 'virtual:paylasim-jpg';
const COZULMUS_KIMLIK = '\0virtual:paylasim-jpg';
const kok = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** `public/` altındaki paylaşım JPG'lerinin site yolları (`/blog-covers/x.jpg`, `/assets/og-cover.jpg`). */
export function paylasimJpgListesi(publicDizini = path.join(kok, 'public')) {
  const liste = [];
  if (fs.existsSync(path.join(publicDizini, 'assets', 'og-cover.jpg'))) liste.push('/assets/og-cover.jpg');
  const kapaklar = path.join(publicDizini, 'blog-covers');
  if (fs.existsSync(kapaklar)) {
    for (const ad of fs.readdirSync(kapaklar)) {
      if (ad.endsWith('.jpg')) liste.push(`/blog-covers/${ad}`);
    }
  }
  return liste.sort();
}

export function paylasimJpgEklentisi() {
  return {
    name: 'mk-paylasim-jpg',
    resolveId(kimlik) {
      return kimlik === SANAL_KIMLIK ? COZULMUS_KIMLIK : null;
    },
    load(kimlik) {
      if (kimlik !== COZULMUS_KIMLIK) return null;
      return `export default ${JSON.stringify(paylasimJpgListesi())};`;
    },
  };
}
