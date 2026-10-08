import { getAPIBaseURL } from '@/lib/config';
import { RIZA_OLAYI, rizayiOku } from '@/lib/riza';

/**
 * Faz 5K — ortaklık referans kodu (`?ref=<kod>`).
 *
 * KVKK: kod cihazda KALICI olarak (localStorage, 30 gün) YALNIZ ziyaretçi
 * çerez/rıza bandında "Kabul" dediyse saklanır. İzin yoksa yalnız bu sekmenin
 * oturumunda (sessionStorage; sekme kapanınca silinir) durur — sitedeki
 * formlara (iletişim, "Teklif al", Site Analizi, modül talebi) gizli alan ya da
 * önceden dolu "indirim / referans kodu" alanı olarak taşınır, girişten sonra
 * kayıt referansı olarak bir kez gönderilir. Rıza sonradan verilirse oturumdaki
 * kod saklanır; geri alınırsa (Reddet / tercihleri sıfırla) cihazdaki kod silinir.
 *
 * Tıklama: kod ilk görüldüğünde bir kez `POST /api/v1/ortaklik/tiklama`
 * (sunucu ortak başına GÜNLÜK toplamı artırır; IP, çerez kimliği, tarayıcı
 * bilgisi tutulmaz). Adres çubuğundaki `?ref=` sonra temizlenir (paylaşılan
 * bağlantıda yeniden sayılmasın).
 */

/** Rızayla kalıcı (localStorage, 30 gün). */
const ANAHTAR = 'mk_ref_v1';
/** Rızasız, yalnız bu sekmenin oturumu (sessionStorage). */
const OTURUM_ANAHTARI = 'mk_ref_oturum_v1';
/** Girişten sonra kayıt referansı olarak gönderilen kod (oturumda bir kez). */
const KAYIT_ANAHTARI = 'mk_ref_kayit_v1';
export const REFERANS_GUN = 30;
const BICIM = /^[\p{L}\p{N}_-]{3,32}$/u;

let bellek = '';
const sayilan = new Set<string>();

function temiz(ham: string | null | undefined): string {
  const k = (ham || '').replace(/\s+/g, '').slice(0, 32);
  return BICIM.test(k) ? k : '';
}

function oturumaYaz(kod: string): void {
  bellek = kod;
  try {
    sessionStorage.setItem(OTURUM_ANAHTARI, kod);
  } catch {
    /* depolama kapalı: bellekte kalır */
  }
}

function oturumdanOku(): string {
  if (bellek) return bellek;
  try {
    bellek = temiz(sessionStorage.getItem(OTURUM_ANAHTARI));
  } catch {
    /* yoksay */
  }
  return bellek;
}

function cihazaYaz(kod: string): void {
  try {
    localStorage.setItem(ANAHTAR, JSON.stringify({ kod, bitis: Date.now() + REFERANS_GUN * 86400000 }));
  } catch {
    /* depolama kapalı: bellekte kalır */
  }
}

function cihazdanSil(): void {
  try {
    localStorage.removeItem(ANAHTAR);
  } catch {
    /* yoksay */
  }
}

function cihazdanOku(): string {
  try {
    const ham = localStorage.getItem(ANAHTAR);
    if (!ham) return '';
    const v = JSON.parse(ham) as { kod?: string; bitis?: number };
    if (!v?.kod || !v.bitis || v.bitis < Date.now()) {
      cihazdanSil();
      return '';
    }
    return temiz(v.kod);
  } catch {
    return '';
  }
}

/** Bu oturumdaki ya da (rıza varsa) cihazda saklanan kod; yoksa boş. */
export function referansOku(): string {
  const oturum = oturumdanOku();
  if (oturum) return oturum;
  return rizayiOku() === 'kabul' ? cihazdanOku() : '';
}

/** Girişten sonra kayıt referansı olarak gönderilecek kod (bu oturumda gönderilmediyse); yoksa boş. */
export function kayitReferansiBekliyor(): string {
  const kod = referansOku();
  if (!kod) return '';
  try {
    if (sessionStorage.getItem(KAYIT_ANAHTARI) === kod) return '';
  } catch {
    /* yoksay */
  }
  return kod;
}

export function kayitReferansiGonderildi(kod: string): void {
  try {
    sessionStorage.setItem(KAYIT_ANAHTARI, kod);
  } catch {
    /* yoksay */
  }
}

/** Adresteki `?ref=` değerini yakalar; bulunduysa true (çağıran adresi temizleyebilir). */
export function referansYakala(arama: string): boolean {
  let kod = '';
  try {
    kod = temiz(new URLSearchParams(arama).get('ref'));
  } catch {
    return false;
  }
  if (!kod) return false;
  oturumaYaz(kod);
  if (rizayiOku() === 'kabul') cihazaYaz(kod);
  const anahtar = kod.toLocaleUpperCase('tr');
  if (!sayilan.has(anahtar)) {
    sayilan.add(anahtar);
    void fetch(`${getAPIBaseURL()}/api/v1/ortaklik/tiklama`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kod }),
      keepalive: true,
    })
      .then((y) => y.body?.cancel())
      .catch(() => undefined);
  }
  return true;
}

/** Rıza değişince: kabul → oturumdaki kodu cihazda sakla; ret / sıfırla → cihazdaki kodu sil (oturumdaki kalır). */
export function referansRizaDinle(): () => void {
  const dinle = () => {
    if (rizayiOku() === 'kabul') {
      const kod = oturumdanOku();
      if (kod) cihazaYaz(kod);
    } else {
      cihazdanSil();
    }
  };
  // Açılışta da: rıza yoksa (ya da sıfırlandıysa) önceden kalmış kod silinsin.
  dinle();
  window.addEventListener(RIZA_OLAYI, dinle);
  return () => window.removeEventListener(RIZA_OLAYI, dinle);
}
