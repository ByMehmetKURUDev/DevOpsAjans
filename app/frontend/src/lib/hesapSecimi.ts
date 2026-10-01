/**
 * Faz 2E — etkin müşteri hesabı seçimi (hesaplar arası geçiş).
 *
 * Kişi birden çok müşteri hesabında üye olabilir; hangisinde çalıştığını
 * bütün API isteklerine eklenen `X-MK-Hesap` başlığıyla söylüyor. Sunucu
 * üyeliği istek başında doğruluyor (üye değilse 403 — kendi hesabına
 * sessizce düşmüyor). Burada yalnız seçim saklanıyor ve başlık kuruluyor.
 *
 * * Seçim `localStorage`'da, KİŞİYE bağlı (`{kisi, hesap}`): aynı tarayıcıda
 *   başka biri giriş yaparsa eski seçim ona uygulanmaz.
 * * Başlık yalnız müşteri panelindeyken (`/client`) gönderiliyor: herkese
 *   açık sayfalar (vitrin, blog) seçimden etkilenmesin.
 * * Kendi hesabı seçiliyse başlık hiç gönderilmiyor (eski davranış).
 *
 * Bu dosya ana pakette (sdkClient bunu içe aktarıyor): küçük tutulmalı.
 */

export const HESAP_BASLIGI = 'X-MK-Hesap';
const ANAHTAR = 'mk_hesap';
export const HESAP_DEGISTI_OLAYI = 'mk-hesap-degisti';

interface Kayit {
  kisi: string;
  hesap: string;
}

function kayitOku(): Kayit | null {
  try {
    const ham = localStorage.getItem(ANAHTAR);
    if (!ham) return null;
    const k = JSON.parse(ham) as Partial<Kayit>;
    return typeof k?.kisi === 'string' && typeof k?.hesap === 'string' ? { kisi: k.kisi, hesap: k.hesap } : null;
  } catch {
    return null;
  }
}

/** Oturum jetonundaki e-posta (yalnız karşılaştırma için; doğrulama sunucuda). */
export function jetonEpostasi(): string {
  try {
    const jeton = localStorage.getItem('token');
    if (!jeton) return '';
    const parca = jeton.split('.')[1] || '';
    const json = atob(parca.replace(/-/g, '+').replace(/_/g, '/'));
    const e = (JSON.parse(json) as { email?: unknown }).email;
    return typeof e === 'string' ? e.trim().toLowerCase() : '';
  } catch {
    return '';
  }
}

/** Kişinin seçtiği hesap (kendi hesabıysa ya da seçim yoksa ''). */
export function seciliHesap(kisi?: string): string {
  const k = kayitOku();
  const ben = (kisi || jetonEpostasi()).toLowerCase();
  if (!k || !ben || k.kisi !== ben || k.hesap === ben) return '';
  return k.hesap;
}

export function hesapSec(kisi: string, hesap: string): void {
  const ben = kisi.trim().toLowerCase();
  const h = hesap.trim().toLowerCase();
  try {
    if (!h || h === ben) localStorage.removeItem(ANAHTAR);
    else localStorage.setItem(ANAHTAR, JSON.stringify({ kisi: ben, hesap: h }));
  } catch {
    /* gizli sekme: seçim bu sayfa ömrüyle sınırlı kalır */
  }
  try {
    window.dispatchEvent(new CustomEvent(HESAP_DEGISTI_OLAYI, { detail: h === ben ? '' : h }));
  } catch {
    /* tarayıcı dışı */
  }
}

function paneldeMi(): boolean {
  try {
    return /^\/((tr|en|de|ru|zh|hi|ar)\/)?client(\/|$)/.test(window.location.pathname);
  } catch {
    return false;
  }
}

/** İsteğe eklenecek başlık (yoksa boş nesne). */
export function hesapBasliklari(): Record<string, string> {
  if (!paneldeMi()) return {};
  const h = seciliHesap();
  return h ? { [HESAP_BASLIGI]: h } : {};
}
