/**
 * Derleme sonrası: blog için RSS akışı üretir → `dist/rss.xml`.
 *
 * Önceden akış yoktu: `/rss.xml` 404 veriyordu, `/blog/rss.xml` ise
 * `/blog/:slug` kuralına takılıp ana sayfa HTML'ini 200 ile döndürüyordu.
 * Akış; RSS okuyucuları, Google Discover ve yeni yazının sosyal hesaplara
 * otomatik paylaşımı (Zapier, Metricool gibi araçlar RSS'i izliyor) için.
 *
 * Kaynak, prerender ile aynı: `seo/content/*.md` frontmatter'ı.
 *
 * Dosya kökte (`/rss.xml`), `/blog/` altında değil: `_redirects`'teki
 * `/blog/:slug  /  200` yeniden yazma kuralı gerçek dosyadan ÖNCE uygulanıyor
 * (wrangler pages dev ile denendi), `/blog/rss.xml` dosyası kabuk HTML'ine
 * dönüşüyordu. `/blog/rss.xml` ve `/feed` → `/rss.xml` 301 `public/_redirects`'te;
 * o satırlar otomatik bloktan önce geldiği için önce onlar eşleşiyor.
 *
 * Görsel: kapağın JPG eşi varsa (`public/blog-covers/<slug>.jpg`) `enclosure`
 * olarak ekleniyor; paylaşım araçları görseli buradan alıyor.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse as parseYaml } from 'yaml';

import { SITE_URL, SITE_NAME, canonicalUrlPathFor } from '../prerender/site.js';

const kok = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const icerikDizini = path.join(kok, 'seo', 'content');

export const AKIS_YOLU = '/rss.xml';
const AKIS_BASLIGI = `${SITE_NAME} — Blog`;
const AKIS_ACIKLAMASI =
  'SEO, Google Ads ve GA4 ölçümleme, veri yönetimi ve web geliştirme üzerine uygulamaya dönük rehberler.';

export function xmlKacis(metin) {
  return String(metin)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/** `2026-03-04` → RFC 822 (`Wed, 04 Mar 2026 09:00:00 +0300`). Geçersizse null. */
export function rfc822(tarih) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(tarih ?? ''));
  if (!m) return null;
  // Yazılar İstanbul saatiyle yayımlanıyor; saat bilinmediği için 09:00 (+03:00).
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 6, 0, 0));
  if (Number.isNaN(d.getTime())) return null;
  const gunler = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const aylar = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const iki = (n) => String(n).padStart(2, '0');
  return `${gunler[d.getUTCDay()]}, ${iki(d.getUTCDate())} ${aylar[d.getUTCMonth()]} ${d.getUTCFullYear()} 09:00:00 +0300`;
}

/** `seo/content/*.md` → yazı listesi, en yeni önce. Tarihsiz ya da taslak yazı akışa girmez. */
export function yazilariOku(dizin = icerikDizini) {
  return fs
    .readdirSync(dizin)
    .filter((ad) => ad.endsWith('.md'))
    .map((ad) => {
      const ham = fs.readFileSync(path.join(dizin, ad), 'utf8');
      const es = ham.match(/^---\n([\s\S]*?)\n---/);
      const veri = es ? (parseYaml(es[1]) ?? {}) : {};
      return {
        slug: ad.replace(/\.md$/, ''),
        baslik: String(veri.title ?? '').trim(),
        aciklama: String(veri.description ?? '').replace(/\s+/g, ' ').trim(),
        kategori: veri.category ? String(veri.category) : '',
        tarih: veri.date ? String(veri.date) : '',
        taslak: veri.draft === true || veri.noindex === true,
      };
    })
    .filter((y) => y.baslik && rfc822(y.tarih) && !y.taslak)
    .sort((a, b) => (a.tarih === b.tarih ? a.slug.localeCompare(b.slug) : b.tarih.localeCompare(a.tarih)));
}

/** Kapak JPG'si `public/` altında varsa enclosure bilgisi. */
function kapak(slug, publicDizini) {
  const dosya = path.join(publicDizini, 'blog-covers', `${slug}.jpg`);
  if (!fs.existsSync(dosya)) return null;
  return { url: `${SITE_URL}/blog-covers/${slug}.jpg`, boyut: fs.statSync(dosya).size };
}

export function akisUret(yazilar, publicDizini = path.join(kok, 'public')) {
  const blogAdresi = `${SITE_URL}${canonicalUrlPathFor('/blog')}`;
  const sonTarih = yazilar.length ? rfc822(yazilar[0].tarih) : null;
  const ogeler = yazilar.map((y) => {
    const adres = `${SITE_URL}${canonicalUrlPathFor(`/blog/${y.slug}`)}`;
    const gorsel = kapak(y.slug, publicDizini);
    return [
      '    <item>',
      `      <title>${xmlKacis(y.baslik)}</title>`,
      `      <link>${adres}</link>`,
      `      <guid isPermaLink="true">${adres}</guid>`,
      `      <pubDate>${rfc822(y.tarih)}</pubDate>`,
      y.kategori ? `      <category>${xmlKacis(y.kategori)}</category>` : null,
      y.aciklama ? `      <description>${xmlKacis(y.aciklama)}</description>` : null,
      gorsel ? `      <enclosure url="${gorsel.url}" length="${gorsel.boyut}" type="image/jpeg" />` : null,
      '    </item>',
    ]
      .filter(Boolean)
      .join('\n');
  });

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '  <channel>',
    `    <title>${xmlKacis(AKIS_BASLIGI)}</title>`,
    `    <link>${blogAdresi}</link>`,
    `    <description>${xmlKacis(AKIS_ACIKLAMASI)}</description>`,
    '    <language>tr-TR</language>',
    sonTarih ? `    <lastBuildDate>${sonTarih}</lastBuildDate>` : null,
    `    <atom:link href="${SITE_URL}${AKIS_YOLU}" rel="self" type="application/rss+xml" />`,
    '    <image>',
    `      <url>${SITE_URL}/logo192.png</url>`,
    `      <title>${xmlKacis(AKIS_BASLIGI)}</title>`,
    `      <link>${blogAdresi}</link>`,
    '    </image>',
    ...ogeler,
    '  </channel>',
    '</rss>',
    '',
  ]
    .filter((s) => s !== null)
    .join('\n');
}

function calistir() {
  const dist = path.join(kok, 'dist');
  if (!fs.existsSync(dist)) throw new Error('rss-uret: dist/ yok — önce vite build.');
  const yazilar = yazilariOku();
  const hedef = path.join(dist, ...AKIS_YOLU.split('/').filter(Boolean));
  fs.mkdirSync(path.dirname(hedef), { recursive: true });
  fs.writeFileSync(hedef, akisUret(yazilar));
  console.log(`✓ RSS: ${yazilar.length} yazı → dist${AKIS_YOLU}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  calistir();
}
