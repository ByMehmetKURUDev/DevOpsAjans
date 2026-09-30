import { useCallback, useEffect, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { musteriRaporlariniGetir, type MusteriRaporu, type RaporOzeti } from '@/lib/ekip';

/**
 * Müşteri başına talep özeti.
 *
 * Talepler sekmesi "hangi talep geldi" diyor; burası "hangi müşteri
 * ne durumda" diyor. Sıralama açık talep sayısına göre: en çok
 * bekleyen müşteri üstte, çünkü listenin işi kimin sırada olduğunu
 * söylemek.
 */

function tarih(deger?: string | null): string {
  if (!deger) return '—';
  const t = new Date(deger);
  if (Number.isNaN(t.getTime())) return '—';
  return t.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function MusteriRaporlari() {
  const { t } = useTranslation();
  const [satirlar, setSatirlar] = useState<MusteriRaporu[]>([]);
  const [ozet, setOzet] = useState<RaporOzeti | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const sonuc = await musteriRaporlariniGetir();
      setSatirlar(sonuc.musteriler);
      setOzet(sonuc.ozet);
    } catch (e) {
      console.error(e);
      toast.error(t('rapor.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {ozet ? (
          <p className="text-sm text-muted-foreground">
            {t('rapor.ozet', {
              musteri: ozet.musteri_sayisi,
              talep: ozet.toplam_talep,
              acik: ozet.acik_talep,
            })}
          </p>
        ) : (
          <span />
        )}
        <Button variant="ghost" size="sm" className="gap-2" onClick={() => void yukle()}>
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} />
          {t('odeme.yenile')}
        </Button>
      </div>

      {yukleniyor ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      ) : satirlar.length === 0 ? (
        <div className="rounded-xl glass p-8 text-center text-sm text-muted-foreground">
          {t('rapor.bosliste')}
        </div>
      ) : (
        <div className="grid gap-3">
          {satirlar.map((m) => (
            <div key={m.client_email} className="rounded-xl glass p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-[200px]">
                  <p className="font-semibold">{m.client_name || m.client_email}</p>
                  <p className="break-all text-xs text-muted-foreground">
                    {m.client_email} • {t('rapor.sonHareket')}: {tarih(m.son_hareket)}
                  </p>
                </div>
                <div className="flex items-center gap-4 text-sm tabular-nums">
                  <span className="text-orange-300" title={t('ui.status.open')}>
                    {m.acik} {t('rapor.acik')}
                  </span>
                  <span className="text-emerald-300" title={t('ui.status.answered')}>
                    {m.cevaplanan} {t('rapor.cevaplanan')}
                  </span>
                  <span className="text-muted-foreground">
                    {m.kapali} {t('rapor.kapali')}
                  </span>
                  <span className="font-bold gradient-text">{m.toplam}</span>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(m.hizmetler).map(([h, adet]) => (
                  <span
                    key={h}
                    className="rounded-full border border-white/10 px-2.5 py-0.5 text-[11px] text-muted-foreground"
                  >
                    {t(`talep.hizmetler.${h}`, { defaultValue: h })} · {adet}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
