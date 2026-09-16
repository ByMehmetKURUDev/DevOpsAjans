/**
 * Stil dosyasını üretilen HTML'lerin içine gömer.
 *
 * Derlemeden sonra her sayfanın `<head>`inde şu satır duruyordu:
 *
 *     <link rel="stylesheet" href="/assets/index-xxxx.css">
 *
 * Bu istek oluşturmayı engelliyor: tarayıcı HTML'i alıyor, sonra CSS için
 * ikinci bir gidiş-dönüş yapıyor ve o gelene kadar hiçbir şey çizmiyor.
 * Yavaş mobil bağlantıda PageSpeed bunun ~1800 ms'e mal olduğunu ölçtü.
 *
 * Dosya gzip'lendiğinde ~14 kB; ikinci bir gidiş-dönüşten ucuz. Bu yüzden
 * link kaldırılıp içerik doğrudan `<style>` olarak gömülüyor. Site tek
 * sayfa uygulaması olduğu için ziyaretçi ilk sayfadan sonra zaten yeni
 * HTML indirmiyor, önbellek kaybı pratikte oluşmuyor.
 *
 * CSS dosyası `dist/assets` altında duruyor: servis çalışanı ve doğrudan
 * bağlantı verenler için erişilebilir kalıyor, sadece artık kimse
 * beklemiyor.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

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

const desen = /<link rel="stylesheet"[^>]*href="(\/assets\/[^"]+\.css)"[^>]*>/g;
const onbellek = new Map();
let gomulen = 0;
let atlanan = 0;

for (const dosya of htmlDosyalari(dist)) {
  const html = fs.readFileSync(dosya, 'utf8');
  let eslesmeVar = false;

  const yeni = html.replace(desen, (tam, href) => {
    const cssYolu = path.join(dist, href);
    if (!fs.existsSync(cssYolu)) {
      console.warn('✗ CSS bulunamadı, link bırakıldı:', href);
      return tam;
    }
    if (!onbellek.has(href)) onbellek.set(href, fs.readFileSync(cssYolu, 'utf8'));
    eslesmeVar = true;
    // `</style>` içeren bir CSS `<style>` bloğunu erken kapatabilir.
    const govde = onbellek.get(href).replace(/<\/style>/gi, '<\\/style>');
    return `<style>${govde}</style>`;
  });

  if (eslesmeVar) {
    fs.writeFileSync(dosya, yeni);
    gomulen += 1;
  } else {
    atlanan += 1;
  }
}

const boyut = [...onbellek.values()].reduce((t, s) => t + Buffer.byteLength(s), 0);
console.log(
  `✓ CSS gömüldü: ${gomulen} sayfa (${(boyut / 1024).toFixed(1)} kB stil), ` +
    `${atlanan} sayfada stylesheet linki yoktu.`,
);
