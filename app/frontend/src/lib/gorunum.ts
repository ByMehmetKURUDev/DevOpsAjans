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

/** Etkin görünümü `<html data-gorunum>` olarak uygular. */
export function gorunumUygula(siteAyari?: string): void {
  if (typeof document === 'undefined') return;
  const secim = tarayiciSecimi() ?? (gecerli(siteAyari) ? siteAyari : 'klasik');
  if (document.documentElement.getAttribute('data-gorunum') !== secim) {
    document.documentElement.setAttribute('data-gorunum', secim);
  }
}
