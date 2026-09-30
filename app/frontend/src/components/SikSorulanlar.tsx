import { memo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronDown, MessageCircleQuestion } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Sıkça sorulan sorular.
 *
 * Soru sayısı koddan değil çeviri dosyasından geliyor: `sss.s1..sN` dizisi
 * nerede biterse orada duruyor. Böylece soru eklemek için bileşene
 * dokunmak gerekmiyor.
 *
 * Aynı metinler ana sayfanın FAQPage yapısal verisini de besliyor
 * (`prerender/app.js`) — soru burada değişince arama sonuçlarındaki
 * karşılığı da değişiyor, iki yerde ayrı metin tutulmuyor.
 *
 * Erişilebilirlik: her başlık gerçek bir `button`; `aria-expanded` ve
 * `aria-controls` ile cevabı işaret ediyor, cevap `region` olarak
 * okunuyor. Kapalı cevap DOM'dan çıkarılmıyor, yalnızca gizleniyor —
 * böylece sayfa içi arama (Ctrl+F) metni bulabiliyor.
 */

/** Çeviride karşılığı olan soru sayısı; fazlası sessizce atlanır. */
const EN_FAZLA_SORU = 12;

function SikSorulanlar() {
  const { t } = useTranslation();
  const [acik, setAcik] = useState<number | null>(0);

  const sorular: { no: number; soru: string; cevap: string }[] = [];
  for (let i = 1; i <= EN_FAZLA_SORU; i++) {
    const soru = t(`sss.s${i}.soru`, { defaultValue: '' });
    const cevap = t(`sss.s${i}.cevap`, { defaultValue: '' });
    if (!soru || !cevap) break;
    sorular.push({ no: i, soru, cevap });
  }

  if (sorular.length === 0) return null;

  return (
    <section id="sss" className="alt-bolum relative py-20 md:py-28 border-t border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-3 lg:gap-16">
          {/* Sol: başlık ve yönlendirme */}
          <div className="lg:sticky lg:top-28 lg:self-start">
            <p className="text-xs uppercase tracking-[0.3em] text-purple-300 mb-4">
              {t('sss.sectionTag')}
            </p>
            <h2 className="text-3xl sm:text-4xl font-bold leading-tight">
              {t('sss.title')} <span className="gradient-text">{t('sss.titleHighlight')}</span>
            </h2>
            <p className="mt-5 text-muted-foreground leading-relaxed">{t('sss.desc')}</p>

            <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <MessageCircleQuestion className="h-5 w-5 text-primary" aria-hidden="true" />
              <p className="mt-3 text-sm font-medium">{t('sss.kalanSoru')}</p>
              <p className="mt-1 text-sm text-muted-foreground">{t('sss.kalanSoruDesc')}</p>
              <Link to="/contact" className="mt-4 block">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-10 w-full !bg-transparent border-white/25 hover:border-white/50"
                >
                  {t('sss.cta')}
                </Button>
              </Link>
            </div>
          </div>

          {/* Sağ: akordeon */}
          <ul className="space-y-3 lg:col-span-2">
            {sorular.map(({ no, soru, cevap }, i) => {
              const aktif = acik === i;
              return (
                <li
                  key={no}
                  className={`overflow-hidden rounded-2xl border transition-colors ${
                    aktif ? 'border-primary/40 bg-primary/[0.06]' : 'border-white/10 bg-white/[0.03]'
                  }`}
                >
                  <h3>
                    <button
                      type="button"
                      onClick={() => setAcik(aktif ? null : i)}
                      aria-expanded={aktif}
                      aria-controls={`sss-cevap-${no}`}
                      id={`sss-soru-${no}`}
                      className="flex min-h-[56px] w-full items-center justify-between gap-4 px-5 py-4 text-left"
                    >
                      <span className="font-medium">{soru}</span>
                      <ChevronDown
                        className={`h-5 w-5 flex-none text-muted-foreground transition-transform duration-200 ${
                          aktif ? 'rotate-180 text-primary' : ''
                        }`}
                        aria-hidden="true"
                      />
                    </button>
                  </h3>
                  <div
                    id={`sss-cevap-${no}`}
                    role="region"
                    aria-labelledby={`sss-soru-${no}`}
                    hidden={!aktif}
                    className="px-5 pb-5"
                  >
                    <p className="text-sm leading-relaxed text-muted-foreground">{cevap}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </section>
  );
}

export default memo(SikSorulanlar);
