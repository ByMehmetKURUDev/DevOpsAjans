/**
 * Site görünümü: "klasik" (eski), "modern" (neon kart görünümü) ya da
 * "nebula" (Faz 8N — uzay arka planı, holografik paneller).
 *
 * Herkes için geçerli seçim admin panelindeki Site Ayarları → Görünüm
 * alanından gelir (`site_gorunum`). Varsayılan klasik; ayar yoksa site
 * eskisi gibi görünür.
 *
 * Yöneticinin denemesi için adres çubuğu anahtarı:
 *   ?gorunum=modern  yalnız bu tarayıcıda Modern görünüm
 *   ?gorunum=nebula  yalnız bu tarayıcıda Nebula görünüm
 *   ?gorunum=klasik  yalnız bu tarayıcıda eski görünüm
 *   ?gorunum=site    tarayıcı seçimini sil, sitenin ayarına uy
 *
 * Modern'in stili `src/gorunum-modern.css` (ana stil dosyasında, yalnız
 * `html[data-gorunum="modern"]` altında). Nebula'nınki `src/gorunum-nebula.css`
 * AYRI bir dosya: yalnız Nebula açıkken iner (bkz. `nebulaStiliniYukle`), Klasik
 * ve Modern ziyaretçisi o dosyayı hiç indirmez.
 */
import nebulaStilAdresi from '../gorunum-nebula.css?url';

export type Gorunum = 'klasik' | 'modern' | 'nebula';

/** Geçerli görünümler (panel seçenekleri ve doğrulama için tek liste). */
export const GORUNUMLER: readonly Gorunum[] = ['klasik', 'modern', 'nebula'];

const ANAHTAR = 'gorunum-onizleme';

function gecerli(v: unknown): v is Gorunum {
  return v === 'klasik' || v === 'modern' || v === 'nebula';
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

/**
 * Nebula stil dosyasını (bir kez) ekler.
 *
 * Site ayarı Nebula iken derleme `<link rel="stylesheet">`i prerender HTML'ine
 * zaten basıyor (prerender/gorunum-plugin.js; kritik kuralları css-gomule
 * gömüyor). `index.html`'deki satır içi betik de `?gorunum=nebula` ya da
 * önbellekteki ayar için ilk boyamadan önce ekliyor. Burası son güvence:
 * ayar sonradan Nebula yapıldıysa (eski derleme) ya da betik çalışmadıysa.
 */
function nebulaStiliniYukle(): void {
  if (document.querySelector('link[href*="gorunum-nebula"]')) return;
  const bag = document.createElement('link');
  bag.rel = 'stylesheet';
  bag.href = nebulaStilAdresi;
  document.head.appendChild(bag);
}

/**
 * Etkin görünümü `<html data-gorunum>` olarak uygular.
 *
 * Öncelik: tarayıcı seçimi (?gorunum=, localStorage) → site ayarı (verilen
 * ya da önbellekteki) → HTML'de zaten yazılı değer → klasik.
 *
 * "HTML'de yazılı değer": ayar henüz bilinmiyorsa (ilk ziyaret, önbellek
 * yok) derlemenin `<html data-gorunum="modern|nebula">` olarak bastığı site
 * ayarı korunur. Yoksa ilk ziyaretçi, ayar isteği dönene kadar bir an Klasik
 * görüyordu. Çağıran ayar yüklenmeden `siteAyari` vermemeli (Layout).
 */
export function gorunumUygula(siteAyari?: string): void {
  if (typeof document === 'undefined') return;
  const ayar = siteAyari ?? onbellektekiSiteAyari();
  const yazili = document.documentElement.getAttribute('data-gorunum');
  const secim = tarayiciSecimi() ?? (gecerli(ayar) ? ayar : gecerli(yazili) ? yazili : 'klasik');
  if (secim === 'nebula') nebulaStiliniYukle();
  if (document.documentElement.getAttribute('data-gorunum') !== secim) {
    document.documentElement.setAttribute('data-gorunum', secim);
  }
}
