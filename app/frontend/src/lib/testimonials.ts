import { useSiteSettings } from '@/lib/siteSettings';

/**
 * Müşteri yorumları.
 *
 * Yorumlar KODDA SABİT DEĞİL ve boş başlar: uydurma müşteri yorumu yazmıyoruz.
 * Panelde `testimonials_json` anahtarına JSON dizisi girildiğinde bölüm
 * kendiliğinden görünür, boşken hiç basılmaz.
 *
 * Beklenen biçim:
 *   [{ "name": "Ad Soyad", "role": "Ünvan, Şirket", "quote": "...", "rating": 5 }]
 */
export interface Testimonial {
  name: string;
  role?: string;
  quote: string;
  /** 1-5 arası. Verilmezse yıldız gösterilmez. */
  rating?: number;
  /** Doğrulanabilir bir kaynak (LinkedIn önerisi, Clutch, Google). */
  sourceUrl?: string;
}

/** Panelde girilen JSON'u ayrıştırır. Bozuk veri bölümü kırmaz, boş döner. */
export function parseTestimonials(raw: string | undefined): Testimonial[] {
  if (!raw || !raw.trim()) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is Testimonial =>
          typeof item === 'object' &&
          item !== null &&
          typeof (item as Testimonial).name === 'string' &&
          typeof (item as Testimonial).quote === 'string' &&
          (item as Testimonial).quote.trim().length > 0,
      )
      .map((item) => ({
        name: item.name.trim(),
        role: item.role?.trim() || undefined,
        quote: item.quote.trim(),
        rating:
          typeof item.rating === 'number' && item.rating >= 1 && item.rating <= 5
            ? Math.round(item.rating)
            : undefined,
        sourceUrl: item.sourceUrl?.trim() || undefined,
      }));
  } catch {
    return [];
  }
}

export function useTestimonials(): Testimonial[] {
  const { settings } = useSiteSettings();
  return parseTestimonials(settings.testimonials_json);
}
