import { Quote, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useTestimonials } from '@/lib/testimonials';

/**
 * Müşteri yorumları bölümü.
 *
 * Panelde yorum girilmemişse hiç basılmaz — boş bir "yorumlar" başlığı
 * göstermek, uydurma yorum koymak kadar kötü. Yapısal veri de yalnızca
 * gerçek yorum varsa üretilir.
 */
export default function Testimonials({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const items = useTestimonials();

  if (items.length === 0) return null;

  return (
    <section className={`py-20 border-t border-white/5 ${className}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-10">
          <p className="text-xs uppercase tracking-[0.3em] text-pink-400 mb-4">
            {t('testimonials.sectionTag')}
          </p>
          <h2 className="text-3xl md:text-4xl font-bold">{t('testimonials.title')}</h2>
        </div>

        <ul className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <li
              key={`${item.name}-${item.quote.slice(0, 24)}`}
              className="flex h-full flex-col rounded-2xl border border-white/10 bg-white/[0.03] p-6 transition-colors hover:border-purple-500/40"
            >
              <Quote className="h-6 w-6 text-purple-400/70" aria-hidden="true" />

              {item.rating ? (
                <div
                  className="mt-4 flex gap-0.5"
                  aria-label={t('testimonials.rating', { rating: item.rating })}
                >
                  {Array.from({ length: 5 }, (_, index) => (
                    <Star
                      key={index}
                      className={`h-4 w-4 ${
                        index < item.rating! ? 'fill-amber-400 text-amber-400' : 'text-white/15'
                      }`}
                      aria-hidden="true"
                    />
                  ))}
                </div>
              ) : null}

              <blockquote className="mt-4 flex-1 text-sm leading-7 text-[#b9a9d6]">
                {item.quote}
              </blockquote>

              <figcaption className="mt-6 border-t border-white/5 pt-4">
                <span className="block font-semibold text-white">{item.name}</span>
                {item.role ? (
                  <span className="block text-xs text-muted-foreground">{item.role}</span>
                ) : null}
                {item.sourceUrl ? (
                  <a
                    href={item.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-xs font-semibold text-purple-300 underline underline-offset-4 hover:text-pink-300"
                  >
                    {t('testimonials.source')}
                  </a>
                ) : null}
              </figcaption>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
