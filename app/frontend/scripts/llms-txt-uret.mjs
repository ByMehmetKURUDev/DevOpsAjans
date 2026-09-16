/**
 * `llms.txt` üretir — yapay zekâ ajanları için site haritası.
 *
 * Önceden `mehmetkuru.dev/llms.txt` adresi 137 kB'lık site HTML'ini
 * döndürüyordu: dosya yoktu, `_redirects` içindeki `/* → /index.html`
 * kuralı devreye giriyordu. PageSpeed bunu "llms.txt önerilere uygun
 * değil" diye işaretliyordu.
 *
 * Biçim llmstxt.org'un önerdiği gibi: bir H1, bir özet paragrafı, sonra
 * bağlantı listeleri. Dosya derlemede üretiliyor ki blog yazıları elle
 * güncellenmeyi beklemesin.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse as parseYaml } from 'yaml';

import { SITE_URL, SITE_NAME, canonicalUrlPathFor } from '../prerender/site.js';

const kok = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const icerikDizini = path.join(kok, 'seo', 'content');
const dist = path.join(kok, 'dist');

const adres = (yol) => SITE_URL + canonicalUrlPathFor(yol);

/** Blog yazılarını frontmatter'larından okur. */
function yazilar() {
  return fs
    .readdirSync(icerikDizini)
    .filter((ad) => ad.endsWith('.md'))
    .map((ad) => {
      const ham = fs.readFileSync(path.join(icerikDizini, ad), 'utf8');
      const es = ham.match(/^---\n([\s\S]*?)\n---/);
      const veri = es ? (parseYaml(es[1]) ?? {}) : {};
      return {
        slug: ad.replace(/\.md$/, ''),
        baslik: String(veri.title ?? ad),
        aciklama: String(veri.description ?? '').replace(/\s+/g, ' ').trim(),
        kategori: veri.category ? String(veri.category) : 'Diğer',
      };
    })
    .sort((a, b) => a.baslik.localeCompare(b.baslik, 'tr'));
}

const SAYFALAR = [
  ['Ana sayfa', '/', 'Hizmetlerin özeti, çalışma süreci ve iletişim.'],
  ['Hizmetler', '/services', 'Web geliştirme, özel yazılım, dijital pazarlama ve altyapı hizmetleri.'],
  ['Portfolyo', '/portfolio', 'Tamamlanmış projeler ve vaka çalışmaları.'],
  ['Blog', '/blog', 'SEO, Google Ads, ölçümleme ve web geliştirme rehberleri.'],
  ['İletişim', '/contact', 'İletişim bilgileri ve teklif formu.'],
];

const gruplar = new Map();
for (const y of yazilar()) {
  if (!gruplar.has(y.kategori)) gruplar.set(y.kategori, []);
  gruplar.get(y.kategori).push(y);
}

const satirlar = [];
satirlar.push(`# ${SITE_NAME}`);
satirlar.push('');
satirlar.push(
  '> İstanbul merkezli, web geliştirme, özel yazılım ve dijital pazarlama ' +
    'üzerine çalışan butik bir ajans. Bu dosya, yapay zekâ ajanlarının siteyi ' +
    'tararken içeriği hızlıca bulabilmesi için hazırlandı.',
);
satirlar.push('');
satirlar.push('- Site dili: Türkçe (arayüz ayrıca en, de, ru, ar, hi, zh)');
satirlar.push('- Blog yalnızca Türkçe yayımlanıyor');
satirlar.push(`- Site haritası: ${SITE_URL}/sitemap.xml`);
satirlar.push('');

satirlar.push('## Sayfalar');
satirlar.push('');
for (const [ad, yol, aciklama] of SAYFALAR) {
  satirlar.push(`- [${ad}](${adres(yol)}): ${aciklama}`);
}
satirlar.push('');

for (const [kategori, liste] of [...gruplar].sort((a, b) => a[0].localeCompare(b[0], 'tr'))) {
  satirlar.push(`## Blog — ${kategori}`);
  satirlar.push('');
  for (const y of liste) {
    const ac = y.aciklama.length > 160 ? y.aciklama.slice(0, 157) + '...' : y.aciklama;
    satirlar.push(`- [${y.baslik}](${adres('/blog/' + y.slug)})${ac ? ': ' + ac : ''}`);
  }
  satirlar.push('');
}

const cikti = satirlar.join('\n');
fs.mkdirSync(dist, { recursive: true });
fs.writeFileSync(path.join(dist, 'llms.txt'), cikti);

const yaziSayisi = [...gruplar.values()].reduce((t, l) => t + l.length, 0);
console.log(
  `✓ llms.txt üretildi: ${SAYFALAR.length} sayfa, ${yaziSayisi} blog yazısı, ` +
    `${(Buffer.byteLength(cikti) / 1024).toFixed(1)} kB`,
);
