/**
 * Logo varyantlarını üretir.
 *
 * Kaynak logo 1024x1024 tek parça künye: üstte avatar, altta
 * "BY MEHMET KURU DEV" yazı bandı. Künye HİÇBİR YERDE kırpılmaz —
 * her boyutta tamamı çerçevenin içine küçültülerek yerleştirilir
 * (`fit: 'contain'`). Yuvarlatılmış köşelerin yazı bandının uçlarını
 * yemesi için kenarlarda pay bırakılır.
 *
 *   logo.webp        1024x1024  Nasıl Çalışır bölümü, genel kullanım
 *   logo-mark.webp    512x512   header, footer
 *   og-cover.webp    1200x630   paylaşım görseli
 *   apple-touch-icon / logo192 / logo512 / favicon-32 / favicon-16
 *
 * Yeniden çizim, kırpma ya da düzenleme yapılmaz; yalnızca ölçekleme
 * ve kenar payı eklenir.
 *
 * Çalıştırma: npm run logo -- <kaynak-dosya>
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDir = path.join(root, 'public');
const assetsDir = path.join(publicDir, 'assets');

const source = process.argv[2];
if (!source || !fs.existsSync(source)) {
  console.error('Kaynak logo dosyası verilmedi.  Kullanım: npm run logo -- <dosya>');
  process.exit(1);
}

/** Logonun kendi zemini; pay eklenen alan aynı renkte olmalı ki ek görünmesin. */
const BACKDROP = '#171a1e';

/**
 * Kenar payı oranı. Kare ikonlar yuvarlatılmış çerçevede gösteriliyor;
 * pay olmadan "BY" ve "DEV" uçları köşelerde kesiliyordu.
 */
const PAD_RATIO = 0.06;

/**
 * Künyenin tamamını verilen kare ölçüye, kenar payıyla birlikte sığdırır.
 * Kırpma yok: `contain` görüntünün hiçbir parçasını dışarıda bırakmaz.
 */
function fitSquare(size) {
  const inner = Math.round(size * (1 - PAD_RATIO * 2));
  const pad = Math.round((size - inner) / 2);
  return sharp(source)
    .resize(inner, inner, { fit: 'contain', background: BACKDROP })
    .extend({ top: pad, bottom: pad, left: pad, right: pad, background: BACKDROP })
    .resize(size, size, { fit: 'contain', background: BACKDROP });
}

async function main() {
  fs.mkdirSync(assetsDir, { recursive: true });
  const written = [];

  const add = async (pipeline, file) => {
    const target = path.join(publicDir, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    await pipeline.toFile(target);
    written.push([file, fs.statSync(target).size]);
  };

  // Tam künye — sayfa görseli.
  await add(fitSquare(1024).webp({ quality: 88 }), 'assets/logo.webp');

  // Paylaşım görseli: yatay çerçeve, künye ortada, kenarlar zemin rengi.
  await add(
    sharp(source)
      .resize(560, 560, { fit: 'contain', background: BACKDROP })
      .extend({ top: 35, bottom: 35, left: 320, right: 320, background: BACKDROP })
      .webp({ quality: 86 }),
    'assets/og-cover.webp',
  );

  // Küçük boyutlar — aynı künye, kırpılmadan küçültülmüş hâli.
  await add(fitSquare(512).webp({ quality: 90 }), 'assets/logo-mark.webp');
  await add(fitSquare(180).png(), 'apple-touch-icon.png');
  await add(fitSquare(192).png(), 'logo192.png');
  await add(fitSquare(512).png(), 'logo512.png');
  await add(fitSquare(32).png(), 'favicon-32.png');
  await add(fitSquare(16).png(), 'favicon-16.png');

  console.log('Üretilen dosyalar:');
  for (const [file, size] of written) {
    console.log(`  ${file.padEnd(28)} ${(size / 1024).toFixed(1).padStart(7)} kB`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
