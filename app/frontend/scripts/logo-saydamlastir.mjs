/**
 * Beyaz zeminli logoyu saydam PNG'ye çevirir.
 *
 * Logonun beyaz zeminli sürümünden dışarıdaki beyazı siler, içerideki
 * beyazlara (yazı bandındaki harfler) dokunmaz. Bunu renk eşiğiyle değil
 * kenarlardan başlayan taşma dolgusuyla yapar: harfler siyah bandın
 * içinde kaldığı için dolgu oraya ulaşamaz.
 *
 * Sonuç `public/assets/logo-kaynak.png` — diğer bütün varyantların kaynağı.
 *
 * Çalıştırma: node scripts/logo-saydamlastir.mjs <beyaz-zeminli-dosya>
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = path.join(root, 'public/assets/logo-kaynak.png');

const source = process.argv[2];
if (!source || !fs.existsSync(source)) {
  console.error('Kullanım: node scripts/logo-saydamlastir.mjs <beyaz-zeminli-dosya>');
  process.exit(1);
}

/** Bu eşiğin üstündeki her kanal "zemin beyazı" sayılır. */
const WHITE = 225;

const { data, info } = await sharp(source)
  .ensureAlpha()
  .raw()
  .toBuffer({ resolveWithObject: true });

const { width, height, channels } = info;
const isLight = (i) => data[i] > WHITE && data[i + 1] > WHITE && data[i + 2] > WHITE;

// Kenarlardan içeri doğru taşma dolgusu. Yığın kullanılıyor: 1024x1024'te
// özyineleme çağrı yığınını taşırıyor.
const seen = new Uint8Array(width * height);
const stack = [];

const push = (x, y) => {
  const p = y * width + x;
  if (seen[p] || !isLight(p * channels)) return;
  seen[p] = 1;
  stack.push(p);
};

for (let x = 0; x < width; x += 1) {
  push(x, 0);
  push(x, height - 1);
}
for (let y = 0; y < height; y += 1) {
  push(0, y);
  push(width - 1, y);
}

while (stack.length > 0) {
  const p = stack.pop();
  const x = p % width;
  const y = (p - x) / width;
  if (x > 0) push(x - 1, y);
  if (x < width - 1) push(x + 1, y);
  if (y > 0) push(x, y - 1);
  if (y < height - 1) push(x, y + 1);
}

let cleared = 0;
for (let p = 0; p < seen.length; p += 1) {
  if (seen[p]) {
    data[p * channels + 3] = 0;
    cleared += 1;
  }
}

// Saydam kenarları kırp: varyantlar kendi kenar payını ekliyor.
await sharp(data, { raw: { width, height, channels } }).png().trim().toFile(target);

const out = await sharp(target).metadata();
console.log(
  `Saydamlaştırıldı: ${cleared} piksel silindi, sonuç ${out.width}x${out.height} → ${path.relative(root, target)}`,
);
