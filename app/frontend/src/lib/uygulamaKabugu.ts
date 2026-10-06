import { useCallback, useEffect, useState } from 'react';
import { ekliLazy } from '@/i18n/ekliLazy';
import { iosMu } from '@/lib/webPush';

/**
 * Faz 7M — panellerin "mobil kabuğu": uygulama olarak yükleme ve çevrimdışı açılış.
 *
 * YALNIZ panel sayfaları (yönetici + müşteri) içe aktarır; herkese açık
 * sayfaların giriş paketine girmez. Görünen parçalar (yükleme düğmesi,
 * çevrimdışı şeridi, çevrimdışı iskelet) ayrı bir parçada, metinleri ek paket
 * `panelKabugu` › `uygulama`.
 *
 * Servis çalışanı (`public/sw.js`) `/client` ve `/admin` gezinmelerini ağdan
 * alır, son başarılı iskeleti saklar; bağlantı yokken o iskelet açılır ve
 * panel burada "çevrimdışı" durumunu gösterir. `/api/` hiçbir zaman
 * önbelleğe alınmaz: çevrimdışıyken veri yok, yalnız iskelet var.
 */

// ---------------------------------------------------------------- yükleme isteği

interface KurulumIstemi extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform?: string }>;
}

let istem: KurulumIstemi | null = null;
let yuklendi = false;
const dinleyiciler = new Set<() => void>();
const haberVer = () => dinleyiciler.forEach((f) => f());

// Modül yüklenir yüklenmez dinle: panel parçası indiği anda (düğme parçası
// gelmeden) tarayıcının tek seferlik isteği kaçmasın.
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    // Tarayıcının kendi "yükle" çubuğu yerine panel başlığındaki küçük düğme.
    e.preventDefault();
    istem = e as KurulumIstemi;
    haberVer();
  });
  window.addEventListener('appinstalled', () => {
    istem = null;
    yuklendi = true;
    haberVer();
  });
}

/** Uygulama olarak (ana ekrandan / yüklü pencerede) mı açıldı? */
export function uygulamaModundaMi(): boolean {
  try {
    return (
      ['standalone', 'minimal-ui', 'window-controls-overlay'].some(
        (m) => window.matchMedia?.(`(display-mode: ${m})`).matches,
      ) || (navigator as Navigator & { standalone?: boolean }).standalone === true
    );
  } catch {
    return false;
  }
}

/** "Gösterme" denince 30 gün susar (tarayıcıya özel; okunamazsa düğme görünür). */
const GIZLEME_ANAHTARI = 'mk_uygulama_yukle_gizli';
const OTUZ_GUN = 30 * 24 * 60 * 60 * 1000;

function gizlendiMi(): boolean {
  try {
    const zaman = Number(window.localStorage.getItem(GIZLEME_ANAHTARI));
    return zaman > 0 && Date.now() - zaman < OTUZ_GUN;
  } catch {
    return false;
  }
}

/**
 * `istem`: tarayıcı yüklemeyi sunuyor (Chrome/Edge/Android) — düğme onu açar.
 * `ios`: iPhone/iPad — yükleme yalnız Paylaş › Ana Ekrana Ekle ile; düğme tarifi açar.
 * `gizli`: zaten uygulama olarak açık, yakın zamanda gizlendi ya da tarayıcı desteklemiyor.
 */
export type YuklemeDurumu = 'gizli' | 'istem' | 'ios';

export function useUygulamaYukleme() {
  const [, yenile] = useState(0);
  const [gizlendi, setGizlendi] = useState(gizlendiMi);
  useEffect(() => {
    const f = () => yenile((n) => n + 1);
    dinleyiciler.add(f);
    return () => {
      dinleyiciler.delete(f);
    };
  }, []);

  let durum: YuklemeDurumu = 'gizli';
  if (!gizlendi && !yuklendi && !uygulamaModundaMi()) {
    if (istem) durum = 'istem';
    else if (iosMu()) durum = 'ios';
  }

  const yukle = useCallback(async () => {
    const e = istem;
    if (!e) return;
    istem = null; // tarayıcının isteği tek kullanımlık
    try {
      await e.prompt();
      if ((await e.userChoice).outcome === 'accepted') yuklendi = true;
    } catch {
      /* kullanıcı kapattı ya da tarayıcı reddetti */
    }
    haberVer();
  }, []);

  const gizle = useCallback(() => {
    try {
      window.localStorage.setItem(GIZLEME_ANAHTARI, String(Date.now()));
    } catch {
      /* depolama yok: yalnız bu açılışta gizli */
    }
    setGizlendi(true);
  }, []);

  return { durum, yukle, gizle };
}

// ---------------------------------------------------------------- bağlantı durumu

/** `navigator.onLine` + `online`/`offline` olayları. */
export function useCevrimici(): boolean {
  const [cevrimici, setCevrimici] = useState(() => typeof navigator === 'undefined' || navigator.onLine !== false);
  useEffect(() => {
    const ac = () => setCevrimici(true);
    const kapa = () => setCevrimici(false);
    window.addEventListener('online', ac);
    window.addEventListener('offline', kapa);
    setCevrimici(navigator.onLine !== false);
    return () => {
      window.removeEventListener('online', ac);
      window.removeEventListener('offline', kapa);
    };
  }, []);
  return cevrimici;
}

/** İstek bağlantı yüzünden mi düştü (sunucunun "hayır"ı değil)? */
export function agHatasiMi(hata: unknown): boolean {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return true;
  const h = hata as { code?: string; response?: unknown } | null;
  return !!h && typeof h === 'object' && !h.response && ['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT'].includes(h.code || '');
}

/**
 * Panel çevrimdışı açıldı mı? Oturum isteği (`auth.me`) bağlantı yüzünden
 * düşerse giriş ekranı yerine çevrimdışı iskelet gösterilir; bağlantı gelince
 * (`online`) istek kendiliğinden yinelenir — `deneme` değişir.
 */
export function useCevrimdisiAcilis() {
  const [cevrimdisi, setCevrimdisi] = useState(false);
  const [deneme, setDeneme] = useState(0);
  useEffect(() => {
    if (!cevrimdisi) return;
    const geldi = () => setDeneme((n) => n + 1);
    window.addEventListener('online', geldi);
    return () => window.removeEventListener('online', geldi);
  }, [cevrimdisi]);
  /** Oturum isteğinin sonucu: hata yoksa (ya da sunucu yanıt verdiyse) çevrimdışı değil. */
  const sonuc = useCallback((hata?: unknown) => setCevrimdisi(hata !== undefined && agHatasiMi(hata)), []);
  const yenidenDene = useCallback(() => setDeneme((n) => n + 1), []);
  return { cevrimdisi, deneme, sonuc, yenidenDene };
}

// ---------------------------------------------------------------- panel iskeleti

export type PanelYolu = '/client' | '/admin';

/** Bu sayfada yüklenmiş, adında içerik özeti olan dosyalar (giriş betikleri, parçalar, dil paketleri). */
function yukluVarliklar(): string[] {
  const adresler = new Set<string>();
  try {
    for (const k of performance.getEntriesByType('resource')) adresler.add(k.name);
  } catch {
    /* zamanlama bilgisi yok */
  }
  document
    .querySelectorAll<HTMLScriptElement | HTMLLinkElement>(
      'script[src], link[rel="modulepreload"][href], link[rel="stylesheet"][href]',
    )
    .forEach((e) => adresler.add('src' in e && e.src ? e.src : (e as HTMLLinkElement).href));
  const kok = `${location.origin}/assets/`;
  return [...adresler]
    .filter((a) => a.startsWith(kok) && !a.includes('?'))
    .map((a) => a.slice(location.origin.length))
    .slice(0, 400);
}

/**
 * Servis çalışanından paneli çevrimdışına hazırlamasını ister: panel iskeleti
 * (`/client` ya da `/admin`) ve bu sayfanın yüklediği içerik özetli dosyalar
 * önbellekte yoksa alınır. İlk ziyarette sayfa servis çalışanı devreye
 * girmeden yüklendiği için bu dosyalar kendiliğinden önbelleğe düşmüyordu.
 */
export function panelIskeletiniSakla(panel: PanelYolu): void {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
  // `ready` servis çalışanı etkinleşince çözülür (ilk ziyarette kayıt `load`'dan sonra yapılıyor);
  // kayıt hiç yoksa (geliştirme sunucusu) beklemede kalır, bir şey yapılmaz.
  navigator.serviceWorker.ready
    .then((kayit) => kayit.active?.postMessage({ tip: 'panel-iskeleti', panel, varliklar: yukluVarliklar() }))
    .catch(() => undefined);
}

/** Panel açılınca ve sekme değişince (yeni parçalar inince) iskeleti tazele. */
export function usePanelKabugu(panel: PanelYolu, anahtar?: unknown): void {
  useEffect(() => {
    const zamanlayici = window.setTimeout(() => panelIskeletiniSakla(panel), 2000);
    return () => window.clearTimeout(zamanlayici);
  }, [panel, anahtar]);
}

// ---------------------------------------------------------------- görünen parçalar (tembel)

const parca = () => import('@/components/UygulamaKabugu');
/** Panel başlığındaki küçük "Uygulama olarak yükle" düğmesi (gerekmiyorsa hiç çizilmez). */
export const UygulamaYukleDugmesi = ekliLazy('panelKabugu', () => parca().then((m) => ({ default: m.UygulamaYukle })));
/** Bağlantı yokken ekranın altında duran uyarı şeridi. */
export const CevrimdisiSerit = ekliLazy('panelKabugu', () => parca().then((m) => ({ default: m.CevrimdisiSerit })));
/** Panel çevrimdışı açılınca giriş ekranı yerine gösterilen iskelet. */
export const CevrimdisiIskelet = ekliLazy('panelKabugu', () => parca().then((m) => ({ default: m.CevrimdisiIskelet })));
