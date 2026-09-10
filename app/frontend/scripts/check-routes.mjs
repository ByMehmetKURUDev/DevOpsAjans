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
