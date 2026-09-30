import { useCallback, useEffect, useState } from 'react';
import { FileText, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { kendiRaporlarim, type Rapor } from '@/lib/abonelikler';

/**
 * Müşterinin rapor arşivi.
 *
 * Yalnızca yayınlanmış raporlar geliyor; taslaklar sunucuda
 * süzülüyor. Adres de oturumdan alınıyor, buradan gönderilmiyor.
 */

function donemAdi(donem: string, dil: string): string {
  const [yil, ay] = (donem || '').split('-');
  const y = Number(yil);
  const a = Number(ay);
  if (!y || !a) return donem;
  try {
    return new Date(y, a - 1, 1).toLocaleDateString(dil || 'tr-TR', {
      month: 'long',
      year: 'numeric',
    });
  } catch {
    return donem;
  }
}

export default function RaporArsivi() {
  const { t, i18n } = useTranslation();
  const [raporlar, setRaporlar] = useState<Rapor[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [acik, setAcik] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      setRaporlar(await kendiRaporlarim());
    } catch (e) {
      console.error(e);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (yukleniyor) {
    return (
      <div className="flex justify-center py-10">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (raporlar.length === 0) {
    return (
      <div className="rounded-2xl glass p-8 text-center text-sm text-muted-foreground">
        {t('rapor.musteriBos')}
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {raporlar.map((r) => {
        const acikMi = acik === r.id;
        const metrikler = r.metrikler && typeof r.metrikler === 'object' ? r.metrikler : null;
        return (
          <div key={r.id} className="rounded-2xl glass p-5">
            <button
              type="button"
              onClick={() => setAcik(acikMi ? null : r.id)}
              className="flex w-full flex-wrap items-center justify-between gap-3 text-left"
            >
              <div className="flex items-center gap-3">
                <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
                <div>
                  <p className="font-semibold">
                    {r.baslik ||
                      t(`talep.hizmetler.${r.hizmet || 'genel'}`, {
                        defaultValue: r.hizmet || '',
                      })}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {donemAdi(r.donem, i18n.language)}
                    {r.hizmet
                      ? ` • ${t(`talep.hizmetler.${r.hizmet}`, { defaultValue: r.hizmet })}`
                      : ''}
                  </p>
                </div>
              </div>
              <span className="text-xs text-primary">
                {acikMi ? t('talep.kapat') : t('rapor.oku')}
              </span>
            </button>

            {acikMi ? (
              <div className="mt-4 space-y-3 border-t border-white/10 pt-4">
                <p className="whitespace-pre-wrap text-sm text-foreground">{r.ozet}</p>
                {metrikler ? (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(metrikler).map(([ad, deger]) => (
                      <span
                        key={ad}
                        className="rounded-full border border-white/10 px-3 py-1 text-xs text-muted-foreground"
                      >
                        {ad}: <span className="text-foreground">{String(deger)}</span>
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
