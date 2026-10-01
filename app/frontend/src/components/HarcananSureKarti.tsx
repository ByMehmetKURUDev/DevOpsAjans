import { useEffect, useState } from 'react';
import { Clock3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { musteriSuresi, tarihGoster, type MusteriSureOzeti } from '@/lib/zamanTakibi';

/** Saat: 2,5 gibi; yerel ondalık ayırıcıyla. */
function saat(dk: number, dil: string): string {
  return (Math.round((dk / 60) * 10) / 10).toLocaleString(dil, { maximumFractionDigits: 1 });
}

/**
 * Müşteri › Projeler › proje kartı: harcanan süre (Faz 3Z).
 *
 * Yalnız ONAYLI süre; proje ayarı ("müşteriye harcanan süreyi göster")
 * kapalıysa ya da modül kapalıysa uç 404/403 döner ve kart hiç çizilmez.
 */
export default function HarcananSureKarti({ projeId }: { projeId: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<MusteriSureOzeti | null>(null);

  useEffect(() => {
    let iptal = false;
    musteriSuresi(projeId)
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch(() => {
        if (!iptal) setVeri(null);
      });
    return () => {
      iptal = true;
    };
  }, [projeId]);

  if (!veri) return null;
  const kutular: [string, number][] = [
    [t('zamanTakibi.musteri.toplam'), veri.toplam_dk],
    [t('zamanTakibi.musteri.buAy'), veri.bu_ay_dk],
  ];
  if (typeof veri.faturalanabilir_dk === 'number') kutular.push([t('zamanTakibi.musteri.faturalanabilir'), veri.faturalanabilir_dk]);
  return (
    <div className="mb-3 rounded-xl border border-white/10 bg-white/[0.02] p-3" data-testid={`harcanan-sure-${projeId}`}>
      <p className="mb-2 inline-flex items-center gap-1.5 text-sm font-semibold text-purple-300">
        <Clock3 className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.musteri.baslik')}
      </p>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {kutular.map(([etiket, dk]) => (
          <div key={etiket} className="min-w-0 rounded-lg bg-white/[0.04] p-2">
            <dt className="truncate text-[11px] text-muted-foreground">{etiket}</dt>
            <dd className="text-lg font-semibold tabular-nums">{t('zamanTakibi.musteri.saat', { sayi: saat(dk, dil) })}</dd>
          </div>
        ))}
      </dl>
      {veri.son_kayit && <p className="mt-2 text-[11px] text-muted-foreground">{t('zamanTakibi.musteri.son', { tarih: tarihGoster(veri.son_kayit, dil) })}</p>}
    </div>
  );
}
