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
  sort_order?: number;
  created_at?: string;
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

/** Özellik satırları; boş satırlar atılıyor. */
export function ozellikler(urun: MarketplaceUrunu): string[] {
  return (urun.features || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
}
