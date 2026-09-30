/**
 * Marketplace ürünleri — siteye açık okuma.
 *
 * Ziyaretçiye açık uç `/api/v1/marketplace` kullanılıyor, SDK'nın entity
 * ucu değil: entity ucu okumak için bile oturum istiyor ve taslak ürünleri
 * de döndürebiliyor. Buradan yalnızca yayındaki ürünler geliyor, filtre
 * sunucuda uygulanıyor.
 *
 * `fetch` doğrudan çağrılıyor çünkü adres siteyle aynı origin'de:
 * Cloudflare Pages Function `/api/*` isteklerini arka uca taşıyor.
 * Kimlik başlığına da gerek yok.
 */

export type UrunKategorisi = 'tool' | 'plugin' | 'website' | 'ecommerce' | 'saas';

export interface MarketplaceUrunu {
  id: number;
  title: string;
  slug: string;
  category?: string;
  summary?: string;
  description?: string;
  /** Her satır bir özellik. */
  features?: string;
  price?: string;
  currency?: string;
  price_note?: string;
  delivery_time?: string;
  image_url?: string;
  demo_url?: string;
  badge?: string;
  published?: boolean;
  sort_order?: number;
  /**
   * Dil başına çeviriler: `{ en: { title, summary, ... }, de: {...} }`.
   * Türkçe ana alanlarda; seçili dilde alan boşsa Türkçe gösterilir.
   */
  ceviriler?: Record<string, Partial<Record<CevrilebilirAlan, string>>> | null;
  created_at?: string;
}

/** Panelde dil başına çevrilebilen ürün alanları. */
export const CEVRILEBILIR_ALANLAR = [
  'title',
  'summary',
  'description',
  'features',
  'price_note',
  'delivery_time',
  'badge',
] as const;
export type CevrilebilirAlan = (typeof CEVRILEBILIR_ALANLAR)[number];

/** Türkçe dışında çeviri tutulan diller (panel dil seçicisinin sırası). */
export const CEVIRI_DILLERI = ['en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;

/**
 * Ürün alanını seçili dilde döndürür. Çeviri `ceviriler` içinde; o dilde
 * alan boşsa Türkçe değer gösterilir (boş kart yerine Türkçe metin).
 */
export function yerel(urun: MarketplaceUrunu, alan: CevrilebilirAlan, dil: string): string {
  const kod = (dil || 'tr').slice(0, 2);
  const turkce = urun[alan] ?? '';
  if (kod === 'tr') return turkce;
  const deger = urun.ceviriler?.[kod]?.[alan];
  return typeof deger === 'string' && deger.trim() ? deger : turkce;
}

interface ListeYaniti {
  items?: MarketplaceUrunu[];
  total?: number;
  categories?: string[];
}

/** Sitede sekme olarak gösterilen kategoriler; sıra burada. */
export const KATEGORILER: UrunKategorisi[] = [
  'website',
  'ecommerce',
  'saas',
  'tool',
  'plugin',
];

/** Kategori anahtarı → i18n anahtarı. */
export function kategoriEtiketi(kategori: string): string {
  return `marketplace.kategori.${kategori}`;
}

/**
 * Yayındaki ürünler.
 *
 * Hata durumunda boş dizi dönüyor, fırlatmıyor: arka uç ücretsiz planda
 * uykudan kalkarken ilk istek zaman aşımına düşebiliyor ve bu yüzden
 * bütün sayfanın beyaz ekrana düşmesi olmaz. Çağıran taraf boş listeyi
 * "henüz ürün yok" diye gösteriyor.
 */
export async function urunleriGetir(signal?: AbortSignal): Promise<MarketplaceUrunu[]> {
  try {
    const yanit = await fetch('/api/v1/marketplace', {
      headers: { accept: 'application/json' },
      signal,
    });
    if (!yanit.ok) return [];
    const govde = (await yanit.json()) as ListeYaniti;
    return Array.isArray(govde.items) ? govde.items : [];
  } catch {
    return [];
  }
}

/** Fiyat metni; fiyat boşsa çağıran taraf "Fiyat Alınız" gösteriyor. */
export function fiyatMetni(urun: MarketplaceUrunu): string {
  const ham = (urun.price || '').trim();
  if (!ham) return '';
  // Panelde "300" da yazılabiliyor, "4.500 ₺'den başlar" da. Sayıysa para
  // birimi başına ekleniyor; değilse yazıldığı gibi gösteriliyor --
  // yazılmış bir fiyat metnini parçalamak, hiç göstermemekten kötü.
  const sadeceSayi = /^[\d.,\s]+$/.test(ham);
  if (!sadeceSayi) return ham;
  const birim = (urun.currency || 'USD').trim().toUpperCase();
  const simge = birim === 'TRY' ? '₺' : birim === 'EUR' ? '€' : '$';
  return `${simge}${ham}`;
}

/** Özellik satırları (seçili dilde); boş satırlar atılıyor. */
export function ozellikler(urun: MarketplaceUrunu, dil = 'tr'): string[] {
  return yerel(urun, 'features', dil)
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
}
