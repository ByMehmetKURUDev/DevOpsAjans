import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Wallet } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BelgeHatasi, paraBicimle } from '@/lib/belge';
import { faturaBakiyesi, faturayaUygula, istekAnahtari, type FaturaBakiyeBilgisi } from '@/lib/cuzdan';

/**
 * Faz 5C — Yönetici › Fatura ayrıntısı: müşterinin faturanın para birimindeki bakiyesi ve "Bakiyeden uygula"
 * (tamamı ya da girilen kısım). Ödeme aynı tahsilat yolundan (`payments`, yöntem "bakiye") yazılır.
 */
export default function FaturayaBakiyeUygula({ faturaId, durum, onUygulandi }: { faturaId: number; durum?: string | null; onUygulandi: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [bilgi, setBilgi] = useState<FaturaBakiyeBilgisi | null>(null);
  const [tutar, setTutar] = useState('');
  const [mesgul, setMesgul] = useState(false);
  const anahtar = useRef(istekAnahtari());

  const yukle = useCallback(async () => {
    try {
      const b = await faturaBakiyesi(faturaId);
      setBilgi(b);
      setTutar(b.onerilen > 0 ? b.onerilen.toFixed(2) : '');
    } catch {
      setBilgi(null);
    }
  }, [faturaId]);

  useEffect(() => {
    void yukle();
  }, [yukle, durum]);

  if (!bilgi || (bilgi.bakiye <= 0 && !bilgi.uygulanabilir)) {
    return bilgi && bilgi.neden !== 'fatura_kapali' ? (
      <p className="text-xs text-muted-foreground" data-testid="fatura-bakiye-yok">{t('cuzdan.fatura.yok')}</p>
    ) : null;
  }

  const uygula = async () => {
    setMesgul(true);
    try {
      await faturayaUygula(faturaId, tutar, anahtar.current);
      anahtar.current = istekAnahtari();
      toast.success(t('cuzdan.fatura.uygulandi'));
      onUygulandi();
      await yukle();
    } catch (h) {
      const kod = h instanceof BelgeHatasi ? h.kod : 'genel';
      toast.error(t(`cuzdan.hata.${kod}`, { defaultValue: t('cuzdan.hata.genel') }));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <section className="rounded-lg border border-purple-400/25 bg-purple-500/[0.05] p-3" data-testid="fatura-bakiye-uygula">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <Wallet className="h-4 w-4 text-purple-300" aria-hidden="true" />
        <span className="font-semibold">{t('cuzdan.fatura.baslik')}</span>
        <span className="text-muted-foreground">{t('cuzdan.fatura.bakiye', { pb: bilgi.para_birimi, tutar: paraBicimle(bilgi.bakiye, bilgi.para_birimi, dil) })}</span>
      </p>
      {bilgi.uygulanabilir && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="grid gap-1 text-xs">{t('cuzdan.ode.tutar')}
            <Input type="number" min={0.01} step="0.01" max={Math.min(bilgi.bakiye, bilgi.kalan)} value={tutar}
              onChange={(e) => setTutar(e.target.value)} className="w-40" data-testid="bakiye-uygula-tutar" />
          </label>
          <Button size="sm" className="gap-1" disabled={mesgul || !tutar} onClick={() => void uygula()} data-testid="bakiye-uygula">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}{t('cuzdan.fatura.uygula')}
          </Button>
        </div>
      )}
    </section>
  );
}
