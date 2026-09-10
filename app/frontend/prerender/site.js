/**
 * Site geneli sabitler ve statik sayfaların SEO meta verileri.
 *
 * Burası tek kaynak: `vite.config.ts` bu dosyadan hem prerender route
 * listesini hem sitemap girdilerini hem de `VITE_*` ortam değişkenlerini
 * besler; prerender entry'si de aynı tablodan `<head>` üretir. Böylece
 * başlık/açıklama iki yerde ayrı ayrı tutulmuyor.
 */

export const SITE_URL = 'https://mehmetkuru.dev';
export const SITE_NAME = 'By Mehmet KURU Dev';
export const SITE_LOCALE = 'tr_TR';
export const SITE_LANG = 'tr';

/** Varsayılan paylaşım görseli — site kendi domaininden servis eder. */
export const SITE_OG_IMAGE = `${SITE_URL}/logo.jpeg`;

/**
 * Prerender edilecek statik sayfalar. `path` sonundaki eğik çizgi
 * çıktının `dist/<yol>/index.html` olarak yazılmasını sağlar.
 */
export const STATIC_ROUTES = [
  {
    path: '/',
    routePath: '/',
    title: 'Web Geliştirme ve Dijital Pazarlama | By Mehmet KURU Dev',
    description:
      'Web geliştirme, e-ticaret, SaaS ve dijital pazarlama hizmetleri. React ve TypeScript ile kurulan hızlı, ölçülebilir ve arama motorlarına uygun projeler.',
    priority: 1.0,
  },
  {
    path: '/services/',
    routePath: '/services',
    title: 'Hizmetler: Web Geliştirme, E-Ticaret ve SEO | Mehmet KURU',
    description:
      'Özel web geliştirme, e-ticaret ve SaaS kurulumu, teknik SEO, Google Ads ve ölçümleme. Tek kıdemli lider altında uçtan uca yürütülen hizmetler.',
    priority: 0.9,
  },
  {
    path: '/portfolio/',
    routePath: '/portfolio',
    title: 'Portföy: Web, E-Ticaret ve SaaS Projeleri | Mehmet KURU',
    description:
      'Teslim edilen web uygulamaları, e-ticaret altyapıları, SaaS platformları ve pazarlama siteleri. Her projede kullanılan yaklaşım ve elde edilen sonuçlar.',
    priority: 0.8,
  },
  {
    path: '/contact/',
    routePath: '/contact',
    title: 'İletişim | By Mehmet KURU Dev',
    description:
      'Projenizi konuşmak için yazın. E-posta, WhatsApp veya iletişim formu üzerinden ulaşın; 24 saat içinde dürüst bir değerlendirmeyle dönüş yapılır.',
    priority: 0.7,
  },
];

/** Blog dizini — içeriği markdown'dan geldiği için ayrı tutuluyor. */
export const BLOG_INDEX_ROUTE = {
  path: '/blog/',
  routePath: '/blog',
  title: 'Blog: SEO, Reklam Ölçümleme ve Web Geliştirme Rehberleri',
  description:
    'Teknik SEO, Google Ads ve GA4 ölçümleme, Customer 360 veri yönetimi ve web geliştirme üzerine uygulamaya dönük rehberler.',
  priority: 0.9,
};

/** Arama motorlarına açılmaması gereken uygulama içi route'lar. */
export const NOINDEX_ROUTES = ['/client', '/admin', '/auth/callback', '/auth/error'];

/** Ana sayfada yayınlanan yapısal veri. Yalnızca `/` için üretilir. */
export const ORGANIZATION_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'ProfessionalService',
  name: SITE_NAME,
  url: `${SITE_URL}/`,
  image: `${SITE_URL}/logo.jpeg`,
  description: 'Web geliştirme, özel yazılım ve dijital pazarlama hizmetleri.',
  email: 'by@mehmetkuru.dev',
  telephone: '+90 541 296 58 78',
  priceRange: '$$',
  areaServed: 'TR',
  address: {
    '@type': 'PostalAddress',
    addressCountry: 'TR',
    addressLocality: 'İstanbul',
  },
  founder: {
    '@type': 'Person',
    name: 'Mehmet KURU',
    jobTitle: 'Full-stack Developer & Digital Marketing Specialist',
  },
};

/**
 * Canonical adres biçimi: kök dışında sondaki eğik çizgi yok.
 *
 * `/services` ve `/services/` Google için iki ayrı URL. Sitemap eklentisi
 * üretilen HTML'lerden yolları eğik çizgisiz topluyor; canonical'ın da aynı
 * biçimde olması ikisinin ayrışmasını önlüyor.
 */
export function canonicalPathFor(pathname) {
  const trimmed = pathname.replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
}

/** Verilen yola göre canonical biçiminde mutlak URL üretir. */
export function absoluteUrl(pathname) {
  const normalized = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `${SITE_URL}${canonicalPathFor(normalized)}`;
}
