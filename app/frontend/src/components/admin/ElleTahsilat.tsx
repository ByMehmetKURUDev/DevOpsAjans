import { useState } from 'react';
import { Banknote, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { elleTahsilatKaydet } from '@/lib/odemeler';

/**
 * Fatura satırındaki "elden/havale tahsilat" düğmesi.
 *
 * Kart tahsilatı bağlanana kadar paranın tek geliş yolu bu: havale,
 * EFT ya da elden. Arka uçtaki `POST /api/v1/odeme/elle` zaten
 * çalışıyordu ama panelde düğmesi yoktu, yani gelen para sisteme
 * girmiyordu.
 *
 * Tutar boş bırakılırsa faturanın tamamı tahsil edilmiş sayılıyor;
 * kısmi tahsilatta rakam yazılıyor ve fatura açık kalıyor. Tam tahsilat
 * faturayı `paid` yapıyor ve o faturanın bekleyen ödeme bağlantısını
 * iptal ediyor — aynı para iki kez sayılmasın, gönderilmiş bağlantı
 * ödenmiş faturayı istemeye devam etmesin diye.
 */

type Kanal = 'havale' | 'eft' | 'elden' | 'diger';

const KANALLAR: Kanal[] = ['havale', 'eft', 'elden', 'diger'];

interface Props {
  invoiceId: number;
  /** Faturanın toplam tutarı: alan boş bırakılırsa bu tahsil ediliyor. */
  tutar?: number | null;
  /** Kayıt düştükten sonra listeyi tazelemek için. */
  onKaydedildi?: () => void;
}

export default function ElleTahsilat({ invoiceId, tutar, onKaydedildi }: Props) {
  const { t } = useTranslation();
  const [acik, setAcik] = useState(false);
  const [kanal, setKanal] = useState<Kanal>('havale');
  const [tutarMetni, setTutarMetni] = useState('');
  const [not, setNot] = useState('');
  const [calisiyor, setCalisiyor] = useState(false);

  async function kaydet() {
    const temiz = tutarMetni.trim().replace(',', '.');
    let sayi: number | undefined;
    if (temiz) {
      sayi = Number(temiz);
      if (!Number.isFinite(sayi) || sayi <= 0) {
        toast.error(t('odeme.elle.tutarGecersiz'));
        return;
      }
    }

    setCalisiyor(true);
    try {
      await elleTahsilatKaydet({ invoiceId, tutar: sayi, kanal, not: not.trim() || undefined });
      toast.success(t('odeme.elle.kaydedildi'));
      setAcik(false);
      setTutarMetni('');
      setNot('');
      onKaydedildi?.();
    } catch (hata) {
      console.error(hata);
      toast.error(t('odeme.elle.kaydedilemedi'));
    } finally {
      setCalisiyor(false);
    }
  }

  if (!acik) {
    return (
      <Button size="sm" variant="ghost" className="gap-2 text-xs" onClick={() => setAcik(true)}>
        <Banknote className="h-4 w-4" />
        {t('odeme.elle.dugme')}
      </Button>
    );
  }

  return (
    <div className="flex w-full flex-col gap-3 rounded-lg border border-dashed border-emerald-400/30 bg-emerald-500/[0.04] px-3 py-3">
      <p className="text-xs font-semibold text-emerald-200">{t('odeme.elle.baslik')}</p>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={kanal}
          onChange={(e) => setKanal(e.target.value as Kanal)}
          className="rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white"
          aria-label={t('odeme.elle.kanal')}
        >
          {KANALLAR.map((k) => (
            <option key={k} value={k}>
              {t(`odeme.elle.kanallar.${k}`)}
            </option>
          ))}
        </select>

        <input
          value={tutarMetni}
          onChange={(e) => setTutarMetni(e.target.value)}
          inputMode="decimal"
          placeholder={
            typeof tutar === 'number'
              ? t('odeme.elle.tutarTamami', { tutar })
              : t('odeme.elle.tutar')
          }
          className="w-36 rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white placeholder:text-muted-foreground"
          aria-label={t('odeme.elle.tutar')}
        />

        <input
          value={not}
          onChange={(e) => setNot(e.target.value)}
          placeholder={t('odeme.elle.not')}
          className="min-w-[140px] flex-1 rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-xs text-white placeholder:text-muted-foreground"
          aria-label={t('odeme.elle.not')}
        />
      </div>

      <div className="flex items-center gap-2">
        <Button size="sm" className="gap-2 text-xs" disabled={calisiyor} onClick={() => void kaydet()}>
          {calisiyor ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Banknote className="h-3.5 w-3.5" />}
          {t('odeme.elle.kaydet')}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-xs"
          disabled={calisiyor}
          onClick={() => setAcik(false)}
        >
          {t('odeme.elle.vazgec')}
        </Button>
      </div>
    </div>
  );
}
