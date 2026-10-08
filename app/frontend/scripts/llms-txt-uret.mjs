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
import { kaynakVerisiniYukle } from '../prerender/kaynaklar-yukle.js';
import { kaynakYolu, listeVerisi } from '../prerender/kaynaklar-veri.js';
import { vitrinYapisiniOku } from '../prerender/moduller-yukle.js';
import { modulYolu, paketYolu } from '../prerender/moduller-veri.js';
import { SEO_ARACLARI, seoAracYolu } from '../prerender/seo-araclari-veri.js';

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
  ['Kaynaklar', '/kaynaklar', 'Kullandığımız ve önerdiğimiz yapay zekâ araçları, Claude becerileri ve açık kaynak projeler (7 dilde).'],
  ['Modüller', '/moduller', 'Müşteri portalı modülleri ve sektöre göre hazır paketler; her modülün tanıtımı ve teklif formu (7 dilde).'],
  ['Ücretsiz SEO araçları', '/seo-araclari', 'Kayıt istemeyen ücretsiz SEO kontrol araçları: meta etiketi, Open Graph, Schema, robots.txt, site haritası, yönlendirme, güvenlik başlıkları, SSL, başlık yapısı ve kelime yoğunluğu (7 dilde).'],
  ['İletişim', '/contact', 'İletişim bilgileri ve teklif formu.'],
  ['Gizlilik Politikası ve KVKK Aydınlatma Metni', '/gizlilik', 'Hangi kişisel verilerin, hangi amaç ve hukuki sebeple işlendiği; aktarım, saklama ve KVKK hakları.'],
  ['Kullanım Koşulları', '/kullanim-kosullari', 'Site, müşteri paneli ve hizmetlerin kullanım koşulları.'],
  ['Çerez Politikası', '/cerez-politikasi', 'Kullanılan çerez ve tarayıcı depolama öğeleri; analitik ve pazarlama yalnız onayla.'],
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

// Faz 3K: Kaynaklar — derlemeyle aynı veri (canlı API, olmazsa tohum dosyası).
const kaynaklar = listeVerisi(await kaynakVerisiniYukle(), 'tr');
if (kaynaklar.kaynaklar.length > 0) {
  satirlar.push('## Kaynaklar — yapay zekâ araçları ve açık kaynak projeler');
  satirlar.push('');
  for (const k of kaynaklar.kaynaklar) {
    const ac = k.ozet.length > 160 ? k.ozet.slice(0, 157) + '...' : k.ozet;
    satirlar.push(`- [${k.baslik}](${adres(kaynakYolu('tr', k.slug))})${ac ? ': ' + ac : ''}`);
  }
  satirlar.push('');
}

// Faz 4V: Modül vitrini — yapı modül kaydından (depodaki kopya), adlar ve özetler ek paketlerden.
const ekPaket = (ad) => JSON.parse(fs.readFileSync(path.join(kok, 'src', 'i18n', 'ek', ad, 'tr.json'), 'utf8'))[ad];
const vitrin = vitrinYapisiniOku();
let modulSayisi = 0;
if (vitrin.moduller.length > 0) {
  const modulMetni = ekPaket('modul');
  const vitrinMetni = ekPaket('modulVitrini');
  satirlar.push('## Modüller — işletmeler için portal modülleri');
  satirlar.push('');
  for (const m of vitrin.moduller) {
    const ad = modulMetni.m?.[m.anahtar]?.ad ?? m.anahtar;
    const ozetMetni = vitrinMetni.m?.[m.anahtar]?.ozet ?? '';
    satirlar.push(`- [${ad}](${adres(modulYolu('tr', m.slug))})${ozetMetni ? ': ' + ozetMetni : ''}`);
    modulSayisi += 1;
  }
  satirlar.push('');
  satirlar.push('## Sektör paketleri');
  satirlar.push('');
  for (const p of vitrin.paketler) {
    const metin = vitrinMetni.p?.[p.anahtar] ?? {};
    const icindekiler = p.moduller.map((k) => modulMetni.m?.[k]?.ad ?? k).join(', ');
    satirlar.push(`- [${metin.ad ?? p.anahtar}](${adres(paketYolu('tr', p.slug))}): ${metin.ozet ?? ''} Modüller: ${icindekiler}.`);
  }
  satirlar.push('');
}

// Faz 4S: ücretsiz SEO araçları — adlar ve kısa açıklamalar ek paketten (Türkçe).
const aracMetni = ekPaket('seoAraclari');
satirlar.push('## Ücretsiz SEO araçları');
satirlar.push('');
for (const a of SEO_ARACLARI) {
  const m = aracMetni.arac?.[a.anahtar] ?? {};
  satirlar.push(`- [${m.ad ?? a.slug}](${adres(seoAracYolu('tr', a.slug))}): ${m.kisa ?? ''}`);
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
  `✓ llms.txt üretildi: ${SAYFALAR.length} sayfa, ${kaynaklar.kaynaklar.length} kaynak, ${modulSayisi} modül, ${SEO_ARACLARI.length} SEO aracı, ${yaziSayisi} blog yazısı, ` +
    `${(Buffer.byteLength(cikti) / 1024).toFixed(1)} kB`,
);
