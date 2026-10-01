import { useCallback, useEffect, useRef } from 'react';

/**
 * Faz 2G — kısa yoklama (polling) için TEK yer.
 *
 * Sunucu Render'ın ücretsiz planında (uyuyabilir, tek süreç), ön yüz ile
 * arasında Cloudflare Pages vekili var: WebSocket/SSE güvenilir değil. Bunun
 * yerine kısa aralıklı istek:
 *
 * * `fn` her `aralik` ms'de bir çağrılır; önceki çağrı bitmeden yenisi başlamaz
 *   (yavaş ağda istekler üst üste binmez).
 * * Sekme gizliyken (`document.visibilityState === 'hidden'`) DURUR; görünür
 *   olunca hemen bir tur çalışıp devam eder.
 * * Ağ hatasında üstel geri çekilme: aralık × 2^n (en çok `enUzun`, varsayılan
 *   5 dk). Başarılı ilk istekte normale döner.
 * * Bileşen kapanınca, `etkin` false olunca ya da `aralik`/`anahtar` değişince
 *   zamanlayıcı ve dinleyici temizlenir.
 *
 * Dönen `simdi()` bekleyen turu öne çeker (ör. mesaj gönderince).
 */
export interface YoklamaSecenekleri {
  /** Milisaniye; 0 → kapalı. */
  aralik: number;
  /** false → yoklama yok. */
  etkin?: boolean;
  /** Bağlanınca beklemeden ilk tur (varsayılan true). */
  hemen?: boolean;
  /** Hata sonrası en uzun bekleme (ms). */
  enUzun?: number;
  /** Değişince yoklama baştan kurulur (ör. etkin hesap, seçili konuşma). */
  anahtar?: unknown;
}

function gizliMi(): boolean {
  try {
    return typeof document !== 'undefined' && document.visibilityState === 'hidden';
  } catch {
    return false;
  }
}

export function useYoklama(
  fn: () => Promise<unknown>,
  { aralik, etkin = true, hemen = true, enUzun = 5 * 60 * 1000, anahtar }: YoklamaSecenekleri
): { simdi: () => void } {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const turRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!etkin || !aralik || typeof window === 'undefined') return;
    let aktif = true;
    let zamanlayici: number | null = null;
    let calisiyor = false;
    let bekleyenTur = false;
    let hata = 0;

    const durdur = () => {
      if (zamanlayici !== null) {
        window.clearTimeout(zamanlayici);
        zamanlayici = null;
      }
    };
    const planla = (ms: number) => {
      durdur();
      if (!aktif || gizliMi()) return;
      zamanlayici = window.setTimeout(() => void calistir(), ms);
    };
    const calistir = async () => {
      zamanlayici = null;
      if (!aktif || gizliMi()) return;
      if (calisiyor) {
        bekleyenTur = true; // biten tur hemen bir daha çalışsın
        return;
      }
      calisiyor = true;
      try {
        await fnRef.current();
        hata = 0;
      } catch {
        hata = Math.min(hata + 1, 12);
      } finally {
        calisiyor = false;
      }
      if (!aktif) return;
      if (bekleyenTur) {
        bekleyenTur = false;
        planla(0);
        return;
      }
      planla(hata ? Math.min(aralik * 2 ** hata, enUzun) : aralik);
    };
    const gorunurluk = () => {
      if (gizliMi()) durdur();
      else {
        durdur();
        void calistir();
      }
    };

    turRef.current = () => {
      durdur();
      void calistir();
    };
    document.addEventListener('visibilitychange', gorunurluk);
    if (hemen) void calistir();
    else planla(aralik);

    return () => {
      aktif = false;
      durdur();
      turRef.current = () => {};
      document.removeEventListener('visibilitychange', gorunurluk);
    };
  }, [aralik, etkin, hemen, enUzun, anahtar]);

  const simdi = useCallback(() => turRef.current(), []);
  return { simdi };
}
