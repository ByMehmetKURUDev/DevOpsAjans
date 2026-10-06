/**
 * Yasal sayfalardaki veri sorumlusu bilgileri (Faz 3Y): ayar anahtarları,
 * varsayılanlar ve çözümleme. Koda gömülü kimlik bilgisi yok — değerler
 * yönetici paneli › Site Ayarları › "Yasal bilgiler"den geliyor; burada
 * yalnız boş kaldıklarında kullanılan varsayılanlar var.
 *
 * Kurallar:
 *   * Unvan boşsa "Mehmet KURU (By Mehmet KURU Dev)".
 *   * E-posta boşsa sitenin iletişim e-postası (`contact_email`), o da
 *     boşsa mehmetkuru.dev@gmail.com.
 *   * Adres, KEP, VKN, MERSİS isteğe bağlı: BOŞSA sayfada hiç gösterilmez.
 *   * Son güncelleme boşsa (ya da YYYY-AA-GG değilse) koddaki tarih.
 *
 * Aynı kural prerender'da (canlı API'den okunan ayarlarla) ve tarayıcıda
 * (site ayarları önbelleğiyle) uygulanıyor. Bağımlılığı olmayan düz JS.
 */

export const YASAL_ANAHTARLAR = {
  unvan: 'yasal_unvan',
  eposta: 'yasal_eposta',
  adres: 'yasal_adres',
  kep: 'yasal_kep',
  vkn: 'yasal_vkn',
  mersis: 'yasal_mersis',
  sonGuncelleme: 'yasal_son_guncelleme',
};

export const YASAL_VARSAYILAN = {
  unvan: 'Mehmet KURU (By Mehmet KURU Dev)',
  eposta: 'mehmetkuru.dev@gmail.com',
  // Metinlerin bu sürümünün tarihi. Metin değişince güncellenmeli (ya da panelden).
  sonGuncelleme: '2026-10-06',
};

/** Prerender'ın canlı API'den alacağı anahtarlar (yasal + iletişim e-postası). */
export const YASAL_OKUNAN_ANAHTARLAR = [...Object.values(YASAL_ANAHTARLAR), 'contact_email'];

const temiz = (deger, sinir = 500) => String(deger ?? '').replace(/\s+/g, ' ').trim().slice(0, sinir);
const TARIH = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Ayar haritasından (`{anahtar: değer}`) sayfada gösterilecek bilgiler.
 * Boş isteğe bağlı alanlar '' döner (bileşen onları hiç çizmiyor).
 */
export function yasalBilgileriCoz(ayarlar = {}) {
  const a = ayarlar || {};
  const tarih = temiz(a[YASAL_ANAHTARLAR.sonGuncelleme], 10);
  return {
    unvan: temiz(a[YASAL_ANAHTARLAR.unvan], 200) || YASAL_VARSAYILAN.unvan,
    eposta: temiz(a[YASAL_ANAHTARLAR.eposta], 254) || temiz(a.contact_email, 254) || YASAL_VARSAYILAN.eposta,
    adres: temiz(a[YASAL_ANAHTARLAR.adres]),
    kep: temiz(a[YASAL_ANAHTARLAR.kep], 254),
    vkn: temiz(a[YASAL_ANAHTARLAR.vkn], 40),
    mersis: temiz(a[YASAL_ANAHTARLAR.mersis], 40),
    sonGuncelleme: TARIH.test(tarih) ? tarih : YASAL_VARSAYILAN.sonGuncelleme,
  };
}

/** "2026-10-01" → dile göre uzun tarih ("1 Ekim 2026"). */
export function tarihBicimle(iso, dil) {
  const [y, m, d] = String(iso).split('-').map(Number);
  try {
    return new Intl.DateTimeFormat(dil, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(Date.UTC(y, m - 1, d)));
  } catch {
    return iso;
  }
}
