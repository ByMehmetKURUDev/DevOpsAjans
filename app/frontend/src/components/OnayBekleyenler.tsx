import { useCallback, useEffect, useState } from 'react';
import { BellRing } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import IslemKarari from '@/components/IslemKarari';
import { IslemHatasi, islemlerim, islemlerimKarar, type IslemSonucu, type MusteriIslemi } from '@/lib/imzaliIslem';

/**
 * Müşteri paneli › genel görünümün en üstü: "Onay bekleyenler".
 *
 * E-postadaki imzalı bağlantıyla aynı kararlar, oturumla: müşteri
 * e-postayı bulamasa da panelden kabul/red, onay/revizyon verebiliyor.
 * Bağlantının kendisi sunucudan hiç gelmiyor. Bekleyen yoksa hiçbir şey
 * çizmiyor (yer kaplamıyor).
 */
export default function OnayBekleyenler({ onDegisti }: { onDegisti?: () => void }) {
  const { t } = useTranslation();
  const [liste, setListe] = useState<MusteriIslemi[]>([]);

  const yukle = useCallback(async () => {
    try {
      setListe(await islemlerim());
    } catch {
      setListe([]);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  if (liste.length === 0) return null;

  const karar = (islem: MusteriIslemi) => async (sonuc: IslemSonucu, not?: string) => {
    try {
      await islemlerimKarar(islem.id, sonuc, not);
    } catch (h) {
      if (h instanceof IslemHatasi && (h.durum === 409 || h.durum === 410 || h.durum === 404)) {
        toast.error(t(`islem.hata.${h.kod}`, { defaultValue: t('islem.hata.genel') }));
        await yukle();
        return;
      }
      throw h;
    }
    toast.success(t(`islem.sonucEkrani.${sonuc}.baslik`));
    setListe((l) => l.filter((x) => x.id !== islem.id));
    onDegisti?.();
  };

  return (
    <section className="mb-10" data-testid="onay-bekleyenler" aria-labelledby="onay-bekleyenler-baslik">
      <h2 id="onay-bekleyenler-baslik" className="mb-4 flex items-center gap-2 text-lg font-semibold">
        <BellRing className="h-5 w-5 text-amber-300" aria-hidden="true" />
        {t('islem.musteri.baslik')}
        <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-300">
          {liste.length}
        </span>
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">{t('islem.musteri.aciklama')}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {liste.map((islem) => (
          <IslemKarari
            key={islem.id}
            islem={islem}
            onKarar={karar(islem)}
            kompakt
            testId={`onay-bekleyen-${islem.id}`}
          />
        ))}
      </div>
    </section>
  );
}
