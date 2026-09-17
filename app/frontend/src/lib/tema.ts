/**
 * Renk teması: mor (varsayılan) ya da yeşil.
 *
 * Tema `<html data-tema="...">` niteliğiyle taşınıyor; renkler
 * `index.css` içinde CSS değişkeni olarak tanımlı, Tailwind'in
 * `purple-*` / `pink-*` sınıfları da o değişkenlere bakıyor. Yani tuşa
 * basınca sayfanın tamamı yeniden çizilmeden renk değiştiriyor.
 *
 * Seçim `localStorage`'da duruyor. İlk boyamadan ÖNCE uygulanması
 * gerekiyor, yoksa yeşil seçmiş bir ziyaretçi her açılışta yarım saniye
 * mor görüyor; bunu `index.html` içindeki küçük betik yapıyor. Buradaki
 * kod yalnızca değiştirme ve okuma için.
 */

export type Tema = 'mor' | 'yesil';

export const TEMALAR: Tema[] = ['mor', 'yesil'];

const ANAHTAR = 'mk_tema';

function gecerli(deger: unknown): deger is Tema {
  return deger === 'mor' || deger === 'yesil';
}

/** Şu an uygulanmış tema. Sunucuda (prerender) varsayılana düşer. */
export function temaOku(): Tema {
  if (typeof document === 'undefined') return 'mor';
  const nitelik = document.documentElement.getAttribute('data-tema');
  if (gecerli(nitelik)) return nitelik;
  try {
    const kayit = localStorage.getItem(ANAHTAR);
    if (gecerli(kayit)) return kayit;
  } catch {
    /* Gizli sekmede localStorage erişimi hata verebiliyor. */
  }
  return 'mor';
}

/** Temayı uygular ve hatırlar. */
export function temaYaz(tema: Tema): void {
  if (typeof document === 'undefined') return;
  // Mor varsayılan olduğu için niteliği hiç yazmıyoruz: CSS zaten :root'tan alıyor.
  if (tema === 'mor') document.documentElement.removeAttribute('data-tema');
  else document.documentElement.setAttribute('data-tema', tema);
  try {
    localStorage.setItem(ANAHTAR, tema);
  } catch {
    /* Kaydedilemezse tema yine de bu oturumda geçerli. */
  }
}
