/**
 * Faz 4G — İçerik Güvenliği Politikası (CSP): TEK KAYNAK.
 *
 * Kullananlar:
 *   * `scripts/guvenlik-basliklari.mjs` (derlemenin son adımı) — `public/_headers`
 *     içindeki `Content-Security-Policy: {{CSP}}` satırını bu politikayla
 *     doldurup `dist/_headers`'a yazıyor ve satır içi betik özetlerini denetliyor.
 *   * `functions/kart/[slug].js`, `functions/menu/[slug].js` — `_headers`
 *     Pages Function yanıtlarına uygulanmadığı için bu HTML sayfalarına aynı
 *     başlıkları kendileri ekliyor.
 *
 * GERİ DÖNÜŞ: `CSP_ZORUNLU = false` → başlık adı `Content-Security-Policy-Report-Only`
 * olur (tarayıcı hiçbir şeyi engellemez, yalnız raporlar). Başka bir şey
 * değiştirmeye gerek yok; derleme `dist/_headers`'ı ve Function'lar kendi
 * başlıklarını buna göre yazar.
 *
 * İhlaller `report-uri` / `report-to` ile `POST /api/v1/csp-rapor` ucuna gidiyor;
 * yönetici paneli › Güvenlik › "CSP ihlal raporları" listesinde görünüyor.
 *
 * Satır içi betikler özetle (hash) izinli: `index.html`'deki üç betik, kritik
 * CSS bağlantısındaki `onload` ve `cevrimdisi.html`'deki "yeniden dene"
 * düğmesinin `onclick`'i (olay işleyicileri için `'unsafe-hashes'`). Biri
 * değişirse özet de değişir; zorunlu modda derleme durur (site betiksiz kalmasın).
 *
 * Kod deneme alanı (ana sayfa) ziyaretçinin yazdığı satır içi kodu çalıştırıyor;
 * o yüzden ayrı bir belgede (`public/kod-deneme/index.html`, kendi meta CSP'si,
 * `_headers`'ta bu politika ondan ayrılıyor) ve kum havuzunda (sandbox) çalışıyor.
 *
 * Kaynaklar:
 *   betik    — kendi kökeni, Google Analytics/Ads (gtag), Meta Pixel (onay sonrası)
 *   stil     — kendi kökeni + satır içi (kritik CSS gömülü, React style=) + Google Fonts (ar/hi)
 *   font     — kendi kökeni + fonts.gstatic.com (ar/hi)
 *   görsel   — https: (blog/marketplace görselleri, reklam pikselleri)
 *   bağlantı — kendi kökeni (/api) + Google'ın GA4/Ads CSP rehberindeki ölçüm
 *              uçları (developers.google.com/tag-platform/security/guides/csp;
 *              ülke alan adı: google.com.tr) + Meta
 *   çerçeve  — Google Haritalar (iletişim, rızayla), reklam dönüşüm çerçeveleri
 */

/** Tek anahtar: true → zorunlu (engelleyen) CSP, false → yalnız rapor. */
export const CSP_ZORUNLU = true;

export const CSP_RAPOR_UCU = '/api/v1/csp-rapor';
export const RAPOR_GRUBU = 'csp';

const SATIR_ICI_OZETLER = [
  "'sha256-oqFr/On43q4LbOnWpE/eciGi1ITFYFkDfTBZuPtANFA='",
  "'sha256-NqlEXPWBrmha1dC1xVrYiUGynn+DKTXlF9l62QQtMl8='",
  "'sha256-PCjmZn0yQDGBUSNPN2ty+MWlzJdvWnTmUGsuUU8TjWY='",
  "'unsafe-hashes'",
  "'sha256-F1noxsLOnJhyRSgc0zu5JgzoLjG2BBMaXaSG24k2mRM='",
  "'sha256-9gOBGqEQINNDuds+tkXbNzih6klbz+KeCyxEj4KRLeM='",
];

export const CSP_YONERGELERI = {
  'default-src': ["'self'"],
  'script-src': [
    "'self'",
    ...SATIR_ICI_OZETLER,
    'https://www.googletagmanager.com',
    'https://www.googleadservices.com',
    'https://googleads.g.doubleclick.net',
    'https://www.google.com',
    'https://connect.facebook.net',
  ],
  'style-src': ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
  'font-src': ["'self'", 'data:', 'https://fonts.gstatic.com'],
  'img-src': ["'self'", 'data:', 'blob:', 'https:'],
  'connect-src': [
    "'self'",
    'https://*.google-analytics.com',
    'https://*.analytics.google.com',
    'https://www.googletagmanager.com',
    'https://*.g.doubleclick.net',
    'https://*.google.com',
    'https://www.google.com.tr',
    'https://www.googleadservices.com',
    'https://pagead2.googlesyndication.com',
    'https://ad.doubleclick.net',
    'https://connect.facebook.net',
    'https://www.facebook.com',
  ],
  'frame-src': ["'self'", 'https://www.google.com', 'https://td.doubleclick.net', 'https://www.googletagmanager.com', 'https://www.facebook.com'],
  'worker-src': ["'self'"],
  'manifest-src': ["'self'"],
  'media-src': ["'self'", 'https:'],
  'object-src': ["'none'"],
  'base-uri': ["'self'"],
  'form-action': ["'self'"],
  'frame-ancestors': ["'self'"],
  'report-uri': [CSP_RAPOR_UCU],
  'report-to': [RAPOR_GRUBU],
};

export const CSP_POLITIKASI = Object.entries(CSP_YONERGELERI)
  .map(([ad, degerler]) => `${ad} ${degerler.join(' ')}`)
  .join('; ');

export const CSP_BASLIK_ADI = CSP_ZORUNLU ? 'Content-Security-Policy' : 'Content-Security-Policy-Report-Only';

/** `report-to` grubunun adresi (göreli: önizleme dağıtımlarında da kendi kökenine gider). */
export const RAPORLAMA_UCLARI = `${RAPOR_GRUBU}="${CSP_RAPOR_UCU}"`;

/**
 * HTML yanıtına eklenecek başlıklar (Function'lar için).
 * `cerceveIzni: '*'` → yalnız `frame-ancestors` değişir (Faz 5R: başka sitelere
 * gömülen randevu penceresi `?gomulu=1`); politikanın geri kalanı aynı kalır.
 */
export function cspBasliklari({ cerceveIzni } = {}) {
  const politika = cerceveIzni
    ? Object.entries({ ...CSP_YONERGELERI, 'frame-ancestors': [cerceveIzni] })
        .map(([ad, degerler]) => `${ad} ${degerler.join(' ')}`)
        .join('; ')
    : CSP_POLITIKASI;
  return { [CSP_BASLIK_ADI]: politika, 'Reporting-Endpoints': RAPORLAMA_UCLARI };
}
