/**
 * Derleme sonrası (Parti 14): soft-404'ü kaldırır.
 *
 * Önceden `_redirects` içindeki `/*  /index.html  200` kuralı, dosyası olmayan
 * HER adresi ana sayfa kabuğuyla 200 döndürüyordu. Google `/teklif/`,
 * `/iletisim/` gibi var olmayan adresleri "bulunamadı" ekranıyla ama 200 durum
 * koduyla görüyordu (soft-404).
 *
 * Bu betik:
 *   1. `dist/_redirects` içindeki her yolu yakalayan SPA kuralını siler. Yerine
 *      yalnız istemcide çizilen rotalar için (`spa-yollari.mjs`, tek kaynak)
 *      tek tek `/  200` yeniden yazma kuralı ekler. Hedef `/index.html` değil `/`:
 *      Pages "pretty URL" kuralı `/index.html`'i 308 ile `/`'a yönlendiriyor, yeniden
 *      yazma da bu yönlendirmeyi döndürüyordu (Function'lar da kabuğu `/`'dan alıyor).
 *   2. `dist/404.html` üretir. Cloudflare Pages kurala da dosyaya da uymayan
 *      adreste bu sayfayı 404 durum koduyla veriyor. Sayfa `index.html`
 *      kabuğunun kendisi: kök boşaltılıyor, React istemcide `NotFoundPage`
 *      çiziyor. Ana sayfa SEO etiketleri (canonical, hreflang, og, JSON-LD)
 *      çıkarılıp `noindex` ekleniyor. Satır içi betikler değişmiyor, böylece
 *      CSP özetleri aynı kalıyor.
 *
 * `css-gomule.mjs`'ten SONRA çalışmalı (index.html son hâlini almış olmalı).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { INTENTIONALLY_NOT_PRERENDERED, SONRADAN_EKLENEBILEN } from './spa-yollari.mjs';

export const BLOK_BASI = '# --- spa-ve-404.mjs: istemci rotaları (otomatik, elle düzenlemeyin) ---';
export const BLOK_SONU = '# --- spa-ve-404.mjs: son ---';
// Cloudflare Pages: 100 dinamik (yer tutuculu / joker) kural sınırı. Pay bırak.
const DINAMIK_UST_SINIR = 90;

/** React Router yolu → Cloudflare `_redirects` kaynak yolları (aynı `:ad` söz dizimi). */
export function kaynakYollari(rota) {
  const yol = rota.startsWith('/') ? rota : `/:lang/${rota}`; // dil ağacının göreli rotaları
  const yollar = [yol];
  // Yer tutucusuz tam yollar (`/admin`) sondaki eğik çizgiyle de gelebiliyor.
  if (!yol.includes(':') && !yol.includes('*') && yol !== '/') yollar.push(`${yol}/`);
  return yollar;
}

export function spaKurallari(rotalar = [...INTENTIONALLY_NOT_PRERENDERED, ...SONRADAN_EKLENEBILEN]) {
  const gorulen = new Set();
  const satirlar = [];
  for (const rota of rotalar) {
    for (const kaynak of kaynakYollari(rota)) {
      if (gorulen.has(kaynak)) continue;
      gorulen.add(kaynak);
      satirlar.push(`${kaynak}  /  200`);
    }
  }
  const dinamik = satirlar.filter((s) => /[:*]/.test(s.split(/\s+/)[0])).length;
  if (dinamik > DINAMIK_UST_SINIR) {
    throw new Error(`_redirects: ${dinamik} dinamik kural, Cloudflare sınırına (100) çok yakın.`);
  }
  return satirlar;
}

/**
 * Prerender edilmiş blog yazılarının eğik çizgisiz adresi → eğik çizgili adres (301).
 *
 * `/blog/:slug  /  200` kuralı (panelden sonradan eklenen yazılar için) gerçek
 * dosyadan ÖNCE uygulanıyor: `/blog/seo-nedir` (sonda `/` yok) ana sayfa kabuğunu
 * — ana sayfanın başlığı ve canonical'ıyla — 200 döndürüyordu. Bağlantı eğik
 * çizgisiz paylaşılınca önizlemede ana sayfa çıkıyordu. Bu statik kurallar
 * otomatik blokta `/blog/:slug`'dan önce geliyor; `dist/blog/<slug>/index.html`
 * olan her yazı kendi sayfasına yönleniyor. Statik kural sınırı 2.000.
 */
export function blogYonlendirmeleri(dist) {
  const blog = path.join(dist, 'blog');
  if (!fs.existsSync(blog)) return [];
  return fs
    .readdirSync(blog, { withFileTypes: true })
    .filter((g) => g.isDirectory() && /^[a-z0-9][a-z0-9-]*$/.test(g.name))
    .filter((g) => fs.existsSync(path.join(blog, g.name, 'index.html')))
    .map((g) => `/blog/${g.name}  /blog/${g.name}/  301`)
    .sort();
}

/** Her yolu yakalayan SPA kuralı mı? (`/*  /index.html  200`, boşluk farkıyla) */
function hepsiniYakalarMi(satir) {
  const p = satir.trim().split(/\s+/);
  return p.length >= 2 && p[0] === '/*' && /^\/(index\.html)?$/.test(p[1]);
}

export function yonlendirmeleriYaz(metin, kurallar = spaKurallari()) {
  // Önceki otomatik bloğu ve her yolu yakalayan kuralı çıkar (betik iki kez çalışsa da aynı sonuç).
  const satirlar = metin.split('\n');
  const temiz = [];
  let blokta = false;
  for (const satir of satirlar) {
    if (satir.trim() === BLOK_BASI) { blokta = true; continue; }
    if (satir.trim() === BLOK_SONU) { blokta = false; continue; }
    if (blokta || hepsiniYakalarMi(satir)) continue;
    temiz.push(satir);
  }
  while (temiz.length && temiz[temiz.length - 1].trim() === '') temiz.pop();
  return `${temiz.join('\n')}\n\n${BLOK_BASI}\n${kurallar.join('\n')}\n${BLOK_SONU}\n`;
}

export function sayfa404(indexHtml) {
  let html = indexHtml;
  const kok = html.indexOf('<div id="root">');
  const govdeSonu = html.lastIndexOf('</body>');
  if (kok < 0 || govdeSonu < kok) throw new Error('404.html: index.html içinde <div id="root"> bulunamadı.');
  html = `${html.slice(0, kok)}<div id="root"></div>\n  ${html.slice(govdeSonu)}`;

  const basSonu = html.indexOf('</head>');
  let bas = html.slice(0, basSonu);
  const kalan = html.slice(basSonu);
  bas = bas
    .replace(/<title>[\s\S]*?<\/title>/, '<title>Sayfa bulunamadı | By Mehmet KURU Dev</title>')
    .replace(/\s*<link\s+rel="(?:canonical|alternate)"[^>]*>/g, '')
    .replace(/\s*<meta\s+(?:name|property)="(?:description|robots|og:[^"]*|twitter:[^"]*|fb:[^"]*)"[^>]*>/g, '')
    .replace(/\s*<script type="application\/ld\+json">[\s\S]*?<\/script>/g, '');
  bas = bas.replace(/(<meta charset="[^"]*"\s*\/?>)/i, '$1\n    <meta name="robots" content="noindex">');
  if (!bas.includes('name="robots"')) bas += '    <meta name="robots" content="noindex">\n  ';
  return bas + kalan;
}

function calistir() {
  const kok = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const dist = path.join(kok, 'dist');
  const yonlendirme = path.join(dist, '_redirects');
  const index = path.join(dist, 'index.html');
  if (!fs.existsSync(index)) throw new Error('spa-ve-404: dist/index.html yok — önce vite build.');

  const kurallar = spaKurallari();
  const blogKurallari = blogYonlendirmeleri(dist);
  const eski = fs.existsSync(yonlendirme) ? fs.readFileSync(yonlendirme, 'utf8') : '';
  fs.writeFileSync(yonlendirme, yonlendirmeleriYaz(eski, [...blogKurallari, ...kurallar]));
  fs.writeFileSync(path.join(dist, '404.html'), sayfa404(fs.readFileSync(index, 'utf8')));
  console.log(
    `✓ _redirects: ${kurallar.length} istemci rotası kuralı + ${blogKurallari.length} blog eğik çizgi yönlendirmesi · 404.html üretildi (soft-404 kapalı).`,
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  calistir();
}
