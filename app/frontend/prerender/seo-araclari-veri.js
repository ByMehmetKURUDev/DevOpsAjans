/**
 * Ücretsiz SEO araçları (Faz 4S) — araç listesi ve yol yardımcıları.
 *
 * Tek kaynak: prerender (`prerender/app.js`), vite.config (ayrıntı yolları),
 * llms.txt betiği ve istemci sayfaları bunu okuyor. Arka uçtaki liste
 * (`app/backend/services/seo_araclari.py` ARACLAR ve ARAC_ANAHTARI) aynı sırada
 * ve aynı anahtarlarla olmalı — `tests/backend/test_seo_araclari.py` karşılaştırıyor.
 *
 * `anahtar` → metinler (`src/i18n/ek/seoAraclari` › `arac.<anahtar>`),
 * `slug` → adres (`/seo-araclari/<slug>`) ve API (`POST /api/v1/seo-araclari/<slug>`),
 * `ikon` → lucide simge adı (sayfa bileşeni eşliyor).
 *
 * Bağımlılığı olmayan düz JS.
 */

export const SEO_ARAC_DILLERI = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];
const VARSAYILAN_DIL = 'tr';

export const SEO_ARACLARI = [
  { anahtar: 'meta', slug: 'meta-etiketleri', ikon: 'Tags' },
  { anahtar: 'og', slug: 'open-graph', ikon: 'Share2' },
  { anahtar: 'schema', slug: 'schema-okuyucu', ikon: 'Braces' },
  { anahtar: 'robots', slug: 'robots-txt', ikon: 'Bot' },
  { anahtar: 'sitemap', slug: 'site-haritasi', ikon: 'Network' },
  { anahtar: 'yonlendirme', slug: 'yonlendirme', ikon: 'Route' },
  { anahtar: 'guvenlik', slug: 'guvenlik-basliklari', ikon: 'ShieldCheck' },
  { anahtar: 'ssl', slug: 'ssl-sertifikasi', ikon: 'Lock' },
  { anahtar: 'basliklar', slug: 'baslik-yapisi', ikon: 'Heading' },
  { anahtar: 'kelime', slug: 'kelime-yogunlugu', ikon: 'TextSearch' },
];

/** robots.txt aracının kullanıcı ajanı seçenekleri (arka uçta da izinli; özel değer de girilebilir). */
export const ROBOTS_AJANLARI = [
  'Googlebot', 'Googlebot-Image', 'Bingbot', 'YandexBot', 'Applebot', 'DuckDuckBot',
  'GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended', 'CCBot', '*',
];

/** `/seo-araclari` (tr) ya da `/en/seo-araclari`. */
export function seoAraclariYolu(dil) {
  return dil && dil !== VARSAYILAN_DIL ? `/${dil}/seo-araclari` : '/seo-araclari';
}

export function seoAracYolu(dil, slug) {
  return `${seoAraclariYolu(dil)}/${slug}`;
}

export function seoAracBul(slug) {
  return SEO_ARACLARI.find((a) => a.slug === slug) ?? null;
}

/**
 * Bir yol SEO araçları sayfası mı? `{ dil, slug }` (dizinde slug null) ya da null.
 * `/seo-araclari`, `/seo-araclari/x`, `/en/seo-araclari/x` (sondaki `/` önemsiz).
 */
export function seoAracYolunuCoz(yol) {
  const temiz = String(yol ?? '').split(/[?#]/)[0].replace(/\/+$/, '');
  const e = temiz.match(/^(?:\/([a-z]{2}))?\/seo-araclari(?:\/([^/]+))?$/);
  if (!e) return null;
  const dil = e[1] ?? VARSAYILAN_DIL;
  if (!SEO_ARAC_DILLERI.includes(dil) || (e[1] && dil === VARSAYILAN_DIL)) return null;
  return { dil, slug: e[2] ? decodeURIComponent(e[2]) : null };
}

/** Prerender edilecek bütün araç sayfaları (7 dil × 10 araç), sonda `/` ile. Dizin PAGE_KEYS'ten geliyor. */
export function seoAracDetayYollari() {
  const yollar = [];
  for (const dil of SEO_ARAC_DILLERI) {
    for (const a of SEO_ARACLARI) yollar.push(`${seoAracYolu(dil, a.slug)}/`);
  }
  return yollar;
}
