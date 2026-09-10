/**
 * Logo varyantlarını üretir.
 *
 * Kaynak logo 1024x1024 bir künye: üstte avatar, altta "BY MEHMET KURU DEV"
 * yazı bandı. Bu künye header'daki 40 pikselde okunmaz — yazı tamamen
 * kaybolur. Bu yüzden iki varyant üretiliyor:
 *
 *   logo.webp        tam künye — Nasıl Çalışır sayfası, paylaşım görseli
 *   logo-mark.webp   yalnızca avatar — header, footer, favicon, uygulama ikonu
 *
 * Kırpma kaynak logonun kendi kompozisyonundan alınır; yeniden çizim ya da
 * düzenleme yapılmaz.
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

/** Avatar bölgesi: yazı bandı 545. satırda başlıyor, üstünde biraz pay bırakılıyor. */
const MARK_CROP = { left: 176, top: 96, width: 672, height: 560 };

async function main() {
  fs.mkdirSync(assetsDir, { recursive: true });
  const written = [];

  const add = async (pipeline, file) => {
    const target = path.join(file.startsWith('assets/') ? publicDir : publicDir, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    await pipeline.toFile(target);
    written.push([file, fs.statSync(target).size]);
  };

  // Tam künye — paylaşım ve sayfa görseli.
  await add(sharp(source).resize(1024, 1024, { fit: 'cover' }).webp({ quality: 88 }), 'assets/logo.webp');
  await add(sharp(source).resize(1200, 630, { fit: 'contain', background: '#05010a' }).webp({ quality: 86 }), 'assets/og-cover.webp');

  // Avatar kırpması — küçük boyutlarda okunabilir tek parça.
  const mark = () => sharp(source).extract(MARK_CROP);
  await add(mark().resize(512, 512, { fit: 'cover' }).webp({ quality: 90 }), 'assets/logo-mark.webp');
  await add(mark().resize(180, 180, { fit: 'cover' }).png(), 'apple-touch-icon.png');
  await add(mark().resize(192, 192, { fit: 'cover' }).png(), 'logo192.png');
  await add(mark().resize(512, 512, { fit: 'cover' }).png(), 'logo512.png');
  await add(mark().resize(32, 32, { fit: 'cover' }).png(), 'favicon-32.png');
  await add(mark().resize(16, 16, { fit: 'cover' }).png(), 'favicon-16.png');

  console.log('Üretilen dosyalar:');
  for (const [file, size] of written) {
    console.log(`  ${file.padEnd(28)} ${(size / 1024).toFixed(1).padStart(7)} kB`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
