/**
 * Route senkron denetimi.
 *
 * `prerender/app.js` route ağacını App.tsx'ten ayrı kuruyor: renderToString
 * Suspense'i bekleyemediği için sunucu tarafında lazy() kullanılamıyor.
 * İki ağaç ayrışırsa bir sayfa sessizce prerender kapsamı dışında kalır —
 * canlıdaki "ana sayfanın HTML'i boş" hatası tam olarak buydu.
 *
 * Bu betik her build'den önce iki listeyi karşılaştırır ve ayrışırsa
 * build'i durdurur.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (rel) => fs.readFileSync(path.join(projectRoot, rel), 'utf8');

/** Kaynak dosyadaki `path="..."` değerlerini toplar. */
function extractRoutePaths(source) {
  const paths = new Set();
  for (const match of source.matchAll(/path:\s*'([^']+)'|path="([^"]+)"/g)) {
    const value = match[1] ?? match[2];
    if (value && value !== '*') paths.add(value);
  }
  return paths;
}

const appRoutes = extractRoutePaths(read('src/App.tsx'));
const prerenderRoutes = extractRoutePaths(read('prerender/app.js'));

// Prerender bilinçli olarak kapsamıyor: kimliği doğrulanmış paneller ve
// auth geri dönüş sayfaları arama motorlarına açılmamalı.
const INTENTIONALLY_NOT_PRERENDERED = new Set([
  '/client',
  '/admin',
  '/auth/callback',
  '/auth/error',
  // Ödeme bağlantısı jetona özel: her adres tek bir faturaya ait,
  // önceden üretilecek bir HTML'i yok ve dizine girmemeli.
  '/ode/:jeton',
  // Site analiz raporu da jetona özel (e-postayla gidiyor), noindex.
  '/rapor/:jeton',
  // İmzalı işlem bağlantısı: jetona özel, girişsiz karar sayfası, noindex.
  '/islem/:jeton',
  // Müşterinin durum sayfası: dinamik, müşteriye ait; varsayılan noindex (Faz 2A).
  '/durum/:slug',
  'durum/:slug',
  // Faz 2C: jetona özel dosya paylaşımı ve aylık müşteri raporu (noindex).
  '/paylas/:jeton',
  '/rapor-aylik/:jeton',
  // Faz 2E: hesap ekibi daveti — jetona özel, kişiye özel (noindex).
  '/hesap-davet/:jeton',
  // Faz 3C: gömülebilir CRM formunun doğrudan bağlantısı — dinamik, noindex.
  '/form/:anahtar',
  // Faz 3T: girişsiz teklif ve sözleşme imza sayfaları — jetona özel (noindex).
  '/teklif/:jeton',
  '/sozlesme/:jeton',
  // Faz 4K: dijital kartvizit ve Google yorum sayfası — kişiye/işletmeye ait, dinamik;
  // paylaşım önizlemesini Pages Function yazıyor (functions/kart/[slug].js). Dil önekli
  // adresler köke yönleniyor.
  '/kart/:slug',
  '/yorum/:slug',
  '/:lang/kart/:slug',
  '/:lang/yorum/:slug',
  // Faz 4M: herkese açık QR menü / katalog — dinamik, mağazaya ait; paylaşım
  // önizlemesini Pages Function yazıyor (functions/menu/[slug].js).
  '/menu/:slug',
  // Faz 5R: herkese açık randevu sayfası ve imzalı yönetim bağlantısı — dinamik,
  // sahibine ait; paylaşım önizlemesini Pages Function yazıyor (functions/randevu/[[yol]].js).
  '/randevu/:slug',
  '/randevu/:slug/:tur',
  '/randevu/yonet/:jeton',
]);

const missing = [...appRoutes].filter(
  (route) => !prerenderRoutes.has(route) && !INTENTIONALLY_NOT_PRERENDERED.has(route),
);
const extra = [...prerenderRoutes].filter((route) => !appRoutes.has(route));

if (missing.length > 0 || extra.length > 0) {
  console.error('\n✗ Route listeleri ayrışmış — build durduruldu.\n');
  if (missing.length > 0) {
    console.error('  App.tsx içinde var, prerender/app.js içinde yok:');
    missing.forEach((route) => console.error(`    ${route}`));
    console.error('  → prerender/app.js route ağacına ekleyin (statik import ile).');
    console.error('  → Arama motoruna kapalı kalmalıysa INTENTIONALLY_NOT_PRERENDERED\n');
  }
  if (extra.length > 0) {
    console.error('  prerender/app.js içinde var, App.tsx içinde yok:');
    extra.forEach((route) => console.error(`    ${route}`));
    console.error('  → App.tsx silinmiş bir route için hâlâ HTML üretiliyor.\n');
  }
  process.exit(1);
}

console.log(`✓ Route senkron: ${appRoutes.size} route, prerender kapsamı tutarlı.`);
