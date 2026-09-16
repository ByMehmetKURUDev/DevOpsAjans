/**
 * Kritik stili HTML'in içine gömer, geri kalanını arkadan yükletir.
 *
 * Derlemeden sonra her sayfanın `<head>`inde şu satır duruyordu:
 *
 *     <link rel="stylesheet" href="/assets/index-xxxx.css">
 *
 * Bu istek oluşturmayı engelliyordu: tarayıcı HTML'i alıyor, sonra CSS
 * için ikinci bir gidiş-dönüş yapıyor ve o gelene kadar hiçbir şey
 * çizmiyordu. PageSpeed bunu mobilde ~1800 ms'e mal ediyor diye ölçtü.
 *
 * İlk denemede stil dosyasının TAMAMINI gömmüştüm; engelleme kalktı ama
 * bu sefer 83 kB'ın tamamı her sayfada ayrıştırılıyordu, yani ağdan
 * kazanılan işlemciye geri veriliyordu. Şimdi `beasties` yalnızca o
 * sayfada gerçekten kullanılan kuralları gömüyor, kalan stil dosyası
 * `preload` ile arkadan geliyor ve çizimi bekletmiyor.
 *
 * Stil dosyası `dist/assets` altında olduğu gibi duruyor — servis
 * çalışanı ve doğrudan bağlantı verenler için erişilebilir.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Beasties from 'beasties';

const kok = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(kok, 'dist');

/** dist altındaki bütün .html dosyalarını toplar. */
function htmlDosyalari(dizin) {
  const sonuc = [];
  for (const girdi of fs.readdirSync(dizin, { withFileTypes: true })) {
    const tam = path.join(dizin, girdi.name);
    if (girdi.isDirectory()) sonuc.push(...htmlDosyalari(tam));
    else if (girdi.name.endsWith('.html')) sonuc.push(tam);
  }
  return sonuc;
}

const beasties = new Beasties({
  path: dist,
  publicPath: '/',
  // Kaynak CSS dosyasına dokunma: 99 sayfa aynı dosyayı paylaşıyor,
  // budanırsa bir sonraki sayfa eksik stille kalır.
  pruneSource: false,
  // Kalan stil `preload` ile gelsin, çizimi bekletmesin.
  preload: 'swap',
  // Fontlar zaten kendi sunucumuzdan ve ayrı @font-face dosyalarında.
  inlineFonts: false,
  preloadFonts: false,
  compress: true,
  logLevel: 'silent',
});

const dosyalar = htmlDosyalari(dist);
let islenen = 0;
let atlanan = 0;
let gomuluToplam = 0;

for (const dosya of dosyalar) {
  const html = fs.readFileSync(dosya, 'utf8');
  if (!/<link[^>]+rel="stylesheet"/.test(html)) {
    atlanan += 1;
    continue;
  }
  let cikti;
  try {
    cikti = await beasties.process(html);
  } catch (hata) {
    console.warn(
      '✗ işlenemedi, stylesheet linki bırakıldı:',
      path.relative(dist, dosya),
      hata.message,
    );
    atlanan += 1;
    continue;
  }
  const gomulu = [...cikti.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)]
    .reduce((t, m) => t + Buffer.byteLength(m[1]), 0);
  gomuluToplam += gomulu;
  fs.writeFileSync(dosya, cikti);
  islenen += 1;
}

const ort = islenen ? gomuluToplam / islenen / 1024 : 0;
console.log(
  `✓ Kritik CSS gömüldü: ${islenen} sayfa (sayfa başına ort. ${ort.toFixed(1)} kB), ` +
    `${atlanan} sayfa atlandı.`,
);
