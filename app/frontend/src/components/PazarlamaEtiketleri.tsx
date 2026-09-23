import { useEffect } from 'react';

import { useSiteSettings } from '@/lib/siteSettings';

/**
 * Reklam ve doğrulama etiketleri.
 *
 * Kimlikler panelden geliyor, koda gömülü değil: Google Ads kimliğini
 * değiştirmek için yeniden derleme gerekmiyor. Kimlik boşsa o platformun
 * betiği HİÇ indirilmiyor -- boş bir kimlikle gtag çağırmak sessiz hata
 * üretiyor ve bedavaya 100+ kB indiriyor.
 *
 * Yükleme, index.html'deki GA yaklaşımıyla aynı: sayfa oturduktan sonra,
 * boşta. Reklam betikleri ana iş parçacığını yüz milisaniyelerce meşgul
 * ediyor; ilk boyamanın önüne geçmemeleri gerekiyor.
 *
 * KVKK/GDPR notu: Meta Pixel ve Google Ads ziyaretçi verisi işliyor.
 * Bunları açmadan önce gizlilik metninin güncellenmesi ve -- AB
 * ziyaretçisi varsa -- rıza (consent) mekanizması gerekiyor. Bu bileşen
 * rıza yönetimi YAPMIYOR; yalnızca panelde girilen kimlikleri kuruyor.
 */

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    fbq?: ((...args: unknown[]) => void) & { callMethod?: unknown; queue?: unknown[] };
    _fbq?: unknown;
  }
}

/** Sayfa yerleştikten sonra, boşta çalıştır. */
function bostaCalistir(is: () => void): () => void {
  let iptal = false;
  const baslat = () => {
    if (iptal) return;
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(() => !iptal && is(), { timeout: 5000 });
    } else {
      is();
    }
  };
  const zaman = window.setTimeout(baslat, 4000);
  return () => {
    iptal = true;
    window.clearTimeout(zaman);
  };
}

function gtagHazirla() {
  window.dataLayer = window.dataLayer || [];
  if (!window.gtag) {
    window.gtag = function gtag(...args: unknown[]) {
      window.dataLayer?.push(args);
    };
  }
}

function betikEkle(src: string, id: string) {
  if (document.getElementById(id)) return;
  const s = document.createElement('script');
  s.id = id;
  s.async = true;
  s.src = src;
  document.head.appendChild(s);
}

/** <meta name=... content=...> — aynı ad için tek etiket. */
function metaEkle(ad: string, deger: string) {
  const temiz = deger.trim();
  if (!temiz) return;
  let etiket = document.querySelector<HTMLMetaElement>(`meta[name="${ad}"]`);
  if (!etiket) {
    etiket = document.createElement('meta');
    etiket.name = ad;
    document.head.appendChild(etiket);
  }
  etiket.content = temiz;
}

export default function PazarlamaEtiketleri() {
  const { settings } = useSiteSettings();

  const adsId = (settings.google_ads_id || '').trim();
  const pixelId = (settings.meta_pixel_id || '').trim();
  const googleDogrulama = (settings.google_site_verification || '').trim();
  const bingDogrulama = (settings.bing_site_verification || '').trim();

  // Doğrulama etiketleri hemen: ağır bir şey indirmiyorlar.
  useEffect(() => {
    metaEkle('google-site-verification', googleDogrulama);
    metaEkle('msvalidate.01', bingDogrulama);
  }, [googleDogrulama, bingDogrulama]);

  // Google Ads
  useEffect(() => {
    if (!adsId) return;
    return bostaCalistir(() => {
      gtagHazirla();
      betikEkle(`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(adsId)}`, 'mk-ads');
      window.gtag?.('js', new Date());
      window.gtag?.('config', adsId);
    });
  }, [adsId]);

  // Meta (Facebook) Pixel
  useEffect(() => {
    if (!pixelId) return;
    return bostaCalistir(() => {
      if (!window.fbq) {
        const n = function (...args: unknown[]) {
          // Betik inmeden önceki çağrılar kuyrukta bekliyor.
          const f = n as unknown as { callMethod?: (...a: unknown[]) => void; queue: unknown[] };
          if (f.callMethod) f.callMethod(...args);
          else f.queue.push(args);
        } as unknown as NonNullable<Window['fbq']>;
        (n as unknown as { queue: unknown[] }).queue = [];
        window.fbq = n;
        window._fbq = n;
      }
      betikEkle('https://connect.facebook.net/en_US/fbevents.js', 'mk-pixel');
      window.fbq?.('init', pixelId);
      window.fbq?.('track', 'PageView');
    });
  }, [pixelId]);

  return null;
}
