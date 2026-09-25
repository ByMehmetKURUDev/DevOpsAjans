import { useState } from 'react';
import { Check, Copy, Link2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { baglantiAdresi, odemeBaglantisiUret } from '@/lib/odemeler';

/**
 * Fatura satırındaki "ödeme bağlantısı üret" düğmesi.
 *
 * Kendi durumunu kendi tutuyor: AdminPanel zaten uzun, oraya bir state
 * daha eklemek yerine düğme kendi başına çalışıyor.
 *
 * Aynı faturaya ikinci kez basılırsa arka uç yeni bağlantı üretmiyor,
 * bekleyeni döndürüyor — müşteriye iki farklı adres gitmesin diye.
 */
export default function FaturaOdemeBaglantisi({ invoiceId }: { invoiceId: number }) {
  const { t } = useTranslation();
  const [adres, setAdres] = useState<string | null>(null);
  const [calisiyor, setCalisiyor] = useState(false);
  const [kopyalandi, setKopyalandi] = useState(false);

  async function uret() {
    setCalisiyor(true);
    try {
      const sonuc = await odemeBaglantisiUret(invoiceId);
      setAdres(baglantiAdresi(sonuc.jeton));
    } catch (hata) {
      console.error(hata);
      toast.error(t('odeme.baglantiUretilemedi'));
    } finally {
      setCalisiyor(false);
    }
  }

  async function kopyala() {
    if (!adres) return;
    try {
      await navigator.clipboard.writeText(adres);
      setKopyalandi(true);
      setTimeout(() => setKopyalandi(false), 1600);
    } catch {
      // Pano kapalıysa (izin yok, güvenli olmayan bağlam) metni seçtir.
      toast.message(adres);
    }
  }

  if (!adres) {
    return (
      <Button
        size="sm"
        variant="ghost"
        className="gap-2 text-xs"
        disabled={calisiyor}
        onClick={() => void uret()}
      >
        <Link2 className="h-4 w-4" />
        {calisiyor ? t('odeme.uretiliyor') : t('odeme.baglantiUret')}
      </Button>
    );
  }

  return (
    <div className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-dashed border-primary/30 bg-primary/[0.04] px-3 py-2">
      <code className="flex-1 min-w-[180px] font-mono text-[11px] break-all text-primary">
        {adres}
      </code>
      <Button size="sm" variant="ghost" className="gap-1.5 text-xs" onClick={() => void kopyala()}>
        {kopyalandi ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        {kopyalandi ? t('odeme.kopyalandi') : t('odeme.kopyala')}
      </Button>
    </div>
  );
}
