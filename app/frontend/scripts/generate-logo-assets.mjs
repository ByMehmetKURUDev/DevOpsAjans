/**
 * Logo varyantlarını üretir.
 *
 * Kaynak: `public/assets/logo-kaynak.png` — saydam zeminli, kırpılmış künye
 * (bkz. `scripts/logo-saydamlastir.mjs`). Künye HİÇBİR YERDE kesilmez;
 * her boyutta tamamı çerçevenin içine küçültülerek yerleştirilir.
 *
 *   logo.webp        1024 kare, SAYDAM   → Nasıl Çalışır bölümü, genel kullanım
 *   logo-mark.webp    512 kare, SAYDAM   → header, footer
 *   og-cover.webp    1200x630, koyu zemin → paylaşım görseli (saydamlık desteklenmez)
 *   apple-touch-icon / logo192 / logo512 / favicon-32 / favicon-16 → koyu zemin
 *
 * Saydam varyantlar site zemininin üstünde kutu göstermiyor; ikonlar ise
 * işletim sistemi tarafından çizildiği için opak olmak zorunda.
 *
 * Çalıştırma: npm run logo
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDir = path.join(root, 'public');
const assetsDir = path.join(publicDir, 'assets');

const source = process.argv[2] || path.join(assetsDir, 'logo-kaynak.png');
if (!fs.existsSync(source)) {
  console.error(`Kaynak bulunamadı: ${source}`);
  console.error('Önce: node scripts/logo-saydamlastir.mjs <beyaz-zeminli-dosya>');
  process.exit(1);
}

/** Site zemini (index.html theme-color ile aynı). İkonlarda kullanılır. */
const BACKDROP = '#05010a';

/** Kenar payı: yuvarlatılmış köşeler yazı bandının uçlarını yemesin. */
const PAD_RATIO = 0.05;

/** Künyenin tamamını kare çerçeveye kenar payıyla sığdırır. Kırpma yok. */
function fitSquare(size, { background }) {
  const inner = Math.round(size * (1 - PAD_RATIO * 2));
  return sharp(source)
    .resize(inner, inner, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .extend({
      top: Math.round((size - inner) / 2),
      bottom: size - inner - Math.round((size - inner) / 2),
      left: Math.round((size - inner) / 2),
      right: size - inner - Math.round((size - inner) / 2),
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    })
    .flatten(background ? { background } : false);
}

const transparent = (size) => fitSquare(size, { background: null });
const opaque = (size) => fitSquare(size, { background: BACKDROP });

async function main() {
  fs.mkdirSync(assetsDir, { recursive: true });
  const written = [];

  const add = async (pipeline, file) => {
    const outPath = path.join(publicDir, file);
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    await pipeline.toFile(outPath);
    written.push([file, fs.statSync(outPath).size]);
  };

  // Sayfa içi kullanım — saydam, site zemininin üstünde kutu göstermez.
  await add(transparent(1024).webp({ quality: 90 }), 'assets/logo.webp');
  await add(transparent(512).webp({ quality: 92 }), 'assets/logo-mark.webp');

  // Paylaşım görseli — yatay çerçeve, künye ortada. Saydamlık desteklenmiyor.
  await add(
    sharp(source)
      .resize(540, 540, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .extend({ top: 45, bottom: 45, left: 330, right: 330, background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .flatten({ background: BACKDROP })
      .webp({ quality: 88 }),
    'assets/og-cover.webp',
  );

  // İşletim sistemi ikonları — opak olmak zorunda.
  await add(opaque(180).png(), 'apple-touch-icon.png');

  /*
   * Maskeli ikon (Android uyarlanabilir ikon): işletim sistemi ikonu
   * daireye, kareye ya da damla biçimine kırpabiliyor. Güvenli alan
   * merkezdeki %80 dairedir; künye bu yüzden daha küçük yerleştirilip
   * çevresi zemin rengiyle dolduruluyor — aksi hâlde köşeleri kesiliyor.
   */
  await add(
    sharp(source)
      .resize(300, 300, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .extend({ top: 106, bottom: 106, left: 106, right: 106, background: { r: 0, g: 0, b: 0, alpha: 0 } })
      .flatten({ background: BACKDROP })
      .png(),
    'logo-maskable-512.png',
  );
  await add(opaque(192).png(), 'logo192.png');
  await add(opaque(512).png(), 'logo512.png');
  await add(opaque(32).png(), 'favicon-32.png');
  await add(opaque(16).png(), 'favicon-16.png');

  console.log('Üretilen dosyalar:');
  for (const [file, size] of written) {
    console.log(`  ${file.padEnd(28)} ${(size / 1024).toFixed(1).padStart(7)} kB`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
