/**
 * Site görünümü: "klasik" (eski) ya da "modern" (yeni kart görünümü).
 *
 * Herkes için geçerli seçim admin panelindeki Site Ayarları → Görünüm
 * alanından gelir (`site_gorunum`). Varsayılan klasik; ayar yoksa site
 * eskisi gibi görünür.
 *
 * Yöneticinin denemesi için adres çubuğu anahtarı:
 *   ?gorunum=modern  yalnız bu tarayıcıda yeni görünüm
 *   ?gorunum=klasik  yalnız bu tarayıcıda eski görünüm
 *   ?gorunum=site    tarayıcı seçimini sil, sitenin ayarına uy
 *
 * Stil `src/gorunum-modern.css` içinde ve yalnız `html[data-gorunum="modern"]`
 * altında çalışır; özellik o dosyadan ibaret.
 */
export type Gorunum = 'klasik' | 'modern';

const ANAHTAR = 'gorunum-onizleme';

function gecerli(v: unknown): v is Gorunum {
  return v === 'klasik' || v === 'modern';
}

/** Adres çubuğundaki `?gorunum=` değerini tarayıcı seçimi olarak kaydeder. */
function tarayiciSecimi(): Gorunum | null {
  try {
    const p = new URLSearchParams(window.location.search).get('gorunum');
    if (p === 'site') localStorage.removeItem(ANAHTAR);
    else if (gecerli(p)) localStorage.setItem(ANAHTAR, p);
    const kayit = localStorage.getItem(ANAHTAR);
    return gecerli(kayit) ? kayit : null;
  } catch {
    return null;
  }
}

/**
 * Önbellekteki site ayarı (siteSettings.ts `mk_site_settings_v2`).
 *
 * main.tsx görünümü React'in ilk çiziminden önce uygular; ayar isteği o
 * sırada henüz dönmemiştir. Önbellekteki değer kullanılmazsa Modern
 * sitede sayfa önce Klasik çiziliyor, ayar gelince bütün sayfa yeniden
 * stillenip yerleşiyordu (fazladan iş ve kayma).
 */
function onbellektekiSiteAyari(): string | undefined {
  try {
    const ham = localStorage.getItem('mk_site_settings_v2');
    return ham ? (JSON.parse(ham) as Record<string, string>).site_gorunum : undefined;
  } catch {
    return undefined;
  }
}

/** Etkin görünümü `<html data-gorunum>` olarak uygular. */
export function gorunumUygula(siteAyari?: string): void {
  if (typeof document === 'undefined') return;
  const ayar = siteAyari ?? onbellektekiSiteAyari();
  const secim = tarayiciSecimi() ?? (gecerli(ayar) ? ayar : 'klasik');
  if (document.documentElement.getAttribute('data-gorunum') !== secim) {
    document.documentElement.setAttribute('data-gorunum', secim);
  }
}
