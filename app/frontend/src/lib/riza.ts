/**
 * Ziyaretçi rızası (KVKK / GDPR).
 *
 * Ölçüm ve reklam betikleri ziyaretçi verisi işliyor; her ikisi de açık
 * rıza istiyor. Buradaki kural basit ve tek yerde: rıza "kabul"
 * değilse GA, Google Ads ve Meta Pixel HİÇ yüklenmiyor. Yüklenip
 * "anonim" sayılmıyor, yüklenmiyor.
 *
 * Değer `localStorage` içinde duruyor: sunucuya gitmiyor ve kendisi bir
 * çerez üretmiyor. Reddeden ziyaretçiden geriye ölçüm kaydı kalmıyor.
 *
 * Zorunlu olanlar rızadan bağımsız çalışmaya devam ediyor: oturum
 * jetonu, dil tercihi, keşif özeti. Bunlar sitenin çalışması için
 * gerekli, izleme amacı taşımıyor.
 */

const ANAHTAR = 'mk_riza_v1';
/** Bant cevaplandığında tetiklenen olay; index.html'deki GA da dinliyor. */
export const RIZA_OLAYI = 'mk-riza-verildi';

export type RizaDurumu = 'kabul' | 'red' | 'sorulmadi';

export function rizayiOku(): RizaDurumu {
  try {
    const v = localStorage.getItem(ANAHTAR);
    return v === 'kabul' || v === 'red' ? v : 'sorulmadi';
  } catch {
    // Gizli sekmede erişim hata verebiliyor: sormamış say, izleme açma.
    return 'sorulmadi';
  }
}

export function rizayiYaz(durum: 'kabul' | 'red'): void {
  try {
    localStorage.setItem(ANAHTAR, durum);
  } catch {
    /* Depolama kapalıysa karar bu sekmeyle sınırlı kalır. */
  }
  // Kabul edilince bekleyen betikler hemen kurulsun; reddedilince de
  // dinleyenler durumu yeniden okusun.
  window.dispatchEvent(new CustomEvent(RIZA_OLAYI, { detail: durum }));
}

/** Kararı geri alır; bant yeniden çıkar. */
export function rizayiSifirla(): void {
  try {
    localStorage.removeItem(ANAHTAR);
  } catch {
    /* yoksay */
  }
  window.dispatchEvent(new CustomEvent(RIZA_OLAYI, { detail: 'sorulmadi' }));
}
