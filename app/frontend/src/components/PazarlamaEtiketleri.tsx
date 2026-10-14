import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { donusum, iletisimYontemi, ozelYolMu } from '@/lib/olcum';
import { RIZA_OLAYI, rizayiOku } from '@/lib/riza';
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
 * KVKK/GDPR: Pixel ve Ads ziyaretçi verisi işliyor, ikisi de açık rıza
 * istiyor. Ziyaretçi rıza bandında "Kabul et" demediyse bu betikler HİÇ
 * indirilmiyor -- indirilip "anonim" sayılmıyor, indirilmiyor. Rıza
 * sonradan verilirse `mk-riza-verildi` olayıyla o an kuruluyorlar.
 *
 * Doğrulama etiketleri (Google/Bing) rızadan bağımsız: ziyaretçi verisi
 * işlemiyorlar, yalnızca site sahipliğini kanıtlıyorlar.
 *
 * Parti 13: özel yollarda (paneller, jetonlu bağlantılar — `lib/olcum.ts`)
 * Pixel/Ads hiç kurulmuyor; kurulduysa o sayfalarda PageView gitmiyor
 * (Pixel'in kendi geçmiş izlemesi kapalı, PageView'ı yalnız açık sayfalarda
 * biz gönderiyoruz). Telefon / e-posta / WhatsApp bağlantısına tıklama
 * "Contact" dönüşümü olarak kaydediliyor.
 */

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    fbq?: ((...args: unknown[]) => void) & { callMethod?: unknown; queue?: unknown[]; disablePushState?: boolean };
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
  const [riza, setRiza] = useState(() => rizayiOku());
  const { pathname } = useLocation();
  const ozel = ozelYolMu(pathname);
  const pixelKuruldu = useRef(false);

  useEffect(() => {
    const tazele = () => setRiza(rizayiOku());
    window.addEventListener(RIZA_OLAYI, tazele);
    return () => window.removeEventListener(RIZA_OLAYI, tazele);
  }, []);

  const izleyebilir = riza === 'kabul';

  const adsId = (settings.google_ads_id || '').trim();
  const pixelId = (settings.meta_pixel_id || '').trim();
  const googleDogrulama = (settings.google_site_verification || '').trim();
  const bingDogrulama = (settings.bing_site_verification || '').trim();

  // Doğrulama etiketleri hemen: ağır bir şey indirmiyorlar.
  useEffect(() => {
    metaEkle('google-site-verification', googleDogrulama);
    metaEkle('msvalidate.01', bingDogrulama);
  }, [googleDogrulama, bingDogrulama]);

  // İletişim tıklamaları → "Contact" dönüşümü (yalnız açık sayfalarda; donusum() ayrıca denetliyor).
  useEffect(() => {
    const tikla = (olay: MouseEvent) => {
      const hedef = olay.target instanceof Element ? olay.target.closest('a[href]') : null;
      const yontem = iletisimYontemi(hedef?.getAttribute('href'));
      if (yontem) donusum('contact', { yontem });
    };
    document.addEventListener('click', tikla, { capture: true });
    return () => document.removeEventListener('click', tikla, { capture: true });
  }, []);

  // Pixel kurulduktan sonra açık sayfalar arası geçişte PageView (özel sayfada değil).
  const ilkSayfa = useRef(true);
  useEffect(() => {
    if (ilkSayfa.current) {
      ilkSayfa.current = false;
      return;
    }
    if (pixelKuruldu.current && !ozel) window.fbq?.('track', 'PageView');
  }, [pathname, ozel]);

  // Google Ads
  useEffect(() => {
    if (!adsId || !izleyebilir || ozel) return;
    return bostaCalistir(() => {
      gtagHazirla();
      betikEkle(`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(adsId)}`, 'mk-ads');
      window.gtag?.('js', new Date());
      window.gtag?.('config', adsId);
    });
  }, [adsId, izleyebilir]);

  // Meta (Facebook) Pixel
  useEffect(() => {
    if (!pixelId || !izleyebilir || ozel || pixelKuruldu.current) return;
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
      // SPA geçişlerinde Pixel kendi PageView'ını göndermesin: özel sayfaları biz eliyoruz.
      if (window.fbq) window.fbq.disablePushState = true;
      betikEkle('https://connect.facebook.net/en_US/fbevents.js', 'mk-pixel');
      window.fbq?.('init', pixelId);
      if (!ozelYolMu(window.location.pathname)) window.fbq?.('track', 'PageView');
      pixelKuruldu.current = true;
    });
  }, [pixelId, izleyebilir, ozel]);

  return null;
}
