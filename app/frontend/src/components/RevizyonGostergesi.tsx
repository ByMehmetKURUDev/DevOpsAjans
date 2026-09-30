import { useEffect, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { revizyonSayacim, saatGoster, type RevizyonSayaci } from '@/lib/projeYonetimi';

/**
 * Müşteri › Projeler üstünde "Bu ay revizyon: 3/8 saat" göstergesi (Faz 2B).
 * Ne hak ne kullanım varsa çizilmiyor.
 */
export default function RevizyonGostergesi() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [r, setR] = useState<RevizyonSayaci | null>(null);

  useEffect(() => {
    let iptal = false;
    revizyonSayacim()
      .then((v) => {
        if (!iptal) setR(v);
      })
      .catch(() => {});
    return () => {
      iptal = true;
    };
  }, []);

  if (!r || (r.hak == null && !r.kullanilan)) return null;
  const kullanilan = saatGoster(r.kullanilan, dil);
  const yuzde = r.hak ? Math.min(100, Math.round(((r.kullanilan - r.krediden) / r.hak) * 100)) : 0;

  return (
    <div className="cam-kart mb-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4" data-testid="revizyon-gostergesi">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="inline-flex items-center gap-2 font-medium">
          <RotateCcw className="h-4 w-4 text-purple-300" aria-hidden="true" />
          {r.hak != null
            ? t('gorevler.revizyon.gosterge', { kullanilan, hak: saatGoster(r.hak, dil) })
            : t('gorevler.revizyon.hakYok', { kullanilan })}
        </span>
        <span className={`text-xs ${r.asildi ? 'text-amber-200' : 'text-muted-foreground'}`}>
          {r.asildi
            ? t('gorevler.revizyon.asildiMusteri', { saat: saatGoster(r.asim, dil) })
            : r.kalan != null
              ? t('gorevler.revizyon.kalan', { saat: saatGoster(r.kalan, dil) })
              : ''}
        </span>
      </div>
      {r.hak != null && (
        <div
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={yuzde}
          aria-label={t('gorevler.revizyon.baslik')}
        >
          <div className={`h-full rounded-full ${r.asildi ? 'bg-amber-400' : 'bg-gradient-to-r from-purple-500 to-pink-500'}`} style={{ width: `${yuzde}%` }} />
        </div>
      )}
    </div>
  );
}
