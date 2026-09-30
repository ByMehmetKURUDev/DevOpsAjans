import { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Flag, ListChecks, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { GOREV_DURUMLARI, musteriGorevleri, tarihGoster, type MusteriGorunumu } from '@/lib/projeYonetimi';

const SUTUN_RENGI: Record<string, string> = {
  yapilacak: 'border-white/10',
  suruyor: 'border-sky-400/30',
  incelemede: 'border-amber-400/30',
  tamam: 'border-emerald-400/30',
};

/**
 * Müşteri › Projeler › proje kartı içinde görevler (Faz 2B, salt okunur).
 *
 * Yalnız ajansın "müşteriye görünür" işaretlediği görevler: ilerleme
 * çubuğu, dört sütunlu okunur Kanban ve kilometre taşı zaman çizelgesi.
 * Görev yoksa (ya da modül kapalıysa) hiçbir şey çizilmiyor.
 */
export default function ProjeGorevGorunumu({ projeId }: { projeId: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<MusteriGorunumu | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);

  useEffect(() => {
    let iptal = false;
    musteriGorevleri(projeId)
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch(() => {
        if (!iptal) setVeri(null);
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, [projeId]);

  if (yukleniyor) return <Loader2 className="mb-3 h-4 w-4 animate-spin text-muted-foreground" />;
  if (!veri || veri.gorevler.length === 0) return null;

  const { ilerleme } = veri;
  return (
    <div className="mb-3 min-w-0 space-y-3" data-testid={`musteri-gorevler-${projeId}`}>
      <div>
        <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
            {t('gorevler.musteri.ilerleme', { tamam: ilerleme.tamam, toplam: ilerleme.toplam })}
          </span>
          <span className="font-medium text-emerald-300">{ilerleme.yuzde}%</span>
        </div>
        <div
          className="h-2 overflow-hidden rounded-full bg-white/10"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={ilerleme.yuzde}
          aria-label={t('gorevler.musteri.baslik')}
          data-testid={`gorev-ilerleme-${projeId}`}
        >
          <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-500" style={{ width: `${ilerleme.yuzde}%` }} />
        </div>
      </div>

      <details className="rounded-xl border border-white/10 bg-white/[0.02] p-3" open>
        <summary className="cursor-pointer text-sm font-semibold text-purple-300 hover:text-pink-300">{t('gorevler.musteri.baslik')}</summary>
        <div className="mt-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {GOREV_DURUMLARI.map((d) => {
              const liste = veri.gorevler.filter((g) => g.durum === d).sort((a, b) => a.sira - b.sira || a.id - b.id);
              return (
                <div key={d} className={`rounded-xl border bg-white/[0.02] p-2 ${SUTUN_RENGI[d]}`} role="group" aria-label={t(`gorevler.durum.${d}`)}>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {t(`gorevler.durum.${d}`)} ({liste.length})
                  </p>
                  <ul className="space-y-1.5">
                    {liste.map((g) => (
                      <li key={g.id} className="rounded-lg bg-white/[0.04] p-2 text-xs" data-testid={`musteri-gorev-${g.id}`}>
                        <p className="break-words font-medium">
                          {g.kilometre_tasi && <Flag className="me-1 inline h-3 w-3 text-purple-300" aria-label={t('gorevler.rozet.kilometre')} />}
                          {g.baslik}
                        </p>
                        {(g.bitis_tarihi || g.kontrol.toplam > 0) && (
                          <p className="mt-0.5 text-[10px] text-muted-foreground">
                            {[g.bitis_tarihi ? tarihGoster(g.bitis_tarihi, dil) : null, g.kontrol.toplam ? `☑ ${g.kontrol.tamam}/${g.kontrol.toplam}` : null]
                              .filter(Boolean)
                              .join(' · ')}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
        {veri.kilometre_taslari.length > 0 && (
          <div className="mt-3" data-testid={`kilometre-${projeId}`}>
            <p className="mb-2 text-xs font-semibold">{t('gorevler.musteri.kilometre')}</p>
            <ol className="relative ms-2 space-y-2 border-s border-white/15 ps-4">
              {veri.kilometre_taslari.map((k) => (
                <li key={k.id} className="relative text-xs">
                  <span className="absolute -start-[1.4rem] top-0.5 bg-background">
                    {k.durum === 'tamam' ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" />
                    ) : (
                      <Circle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                    )}
                  </span>
                  <span className="font-medium">{k.baslik}</span>
                  <span className="text-muted-foreground">
                    {' '}
                    · {k.bitis_tarihi ? tarihGoster(k.bitis_tarihi, dil) : t('gorevler.musteri.tarihYok')} · {t(`gorevler.durum.${k.durum}`)}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </details>
    </div>
  );
}
