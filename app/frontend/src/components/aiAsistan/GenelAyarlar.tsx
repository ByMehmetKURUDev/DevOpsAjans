import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, KART } from '@/components/aiAsistan/ortak';
import { hataMetni, type AsistanApi, type GenelAyarlar as Ayarlar } from '@/lib/aiAsistan';

/**
 * Faz 5A — yalnız yönetici: bütün asistanlar için model, sitenin günlük yapay zekâ bütçesi
 * (asistan mesajları), kredi bloğu (aya dahil hak bitince her N mesaj için K kredi),
 * ajansın kendi asistanının günlük sınırı ve gömme (hibrit arama) modeli.
 */

export default function GenelAyarlar({ api }: { api: AsistanApi }) {
  const { t } = useTranslation();
  const [acik, setAcik] = useState(false);
  const [a, setA] = useState<Ayarlar | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  useEffect(() => {
    if (!acik || a) return;
    api
      .genelAyarlar()
      .then(setA)
      .catch((e) => toast.error(hataMetni(t, e)));
  }, [acik, a, api, t]);

  const kaydet = async () => {
    if (!a) return;
    setKaydediliyor(true);
    try {
      setA(
        await api.genelAyarlariYaz({
          model: a.model_ayari,
          gunluk_butce: Number(a.gunluk_butce),
          blok_mesaj: Number(a.blok_mesaj),
          blok_kredi: Number(a.blok_kredi),
          ajans_gunluk: Number(a.ajans_gunluk),
          gomme_modeli: a.gomme_modeli,
        })
      );
      toast.success(t('aiAsistan.ayar.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <div className={`${KART} p-4`} data-testid="ai-genel-ayarlar">
      <button type="button" className="flex w-full items-center gap-2 text-start" onClick={() => setAcik(!acik)} aria-expanded={acik}>
        <span className="flex-1 font-semibold">{t('aiAsistan.genel.baslik')}</span>
        <ChevronDown className={`h-4 w-4 transition-transform ${acik ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {acik && !a && <Loader2 className="mt-3 h-4 w-4 animate-spin" aria-hidden="true" />}
      {acik && a && (
        <div className="mt-4 space-y-4">
          <p className="text-xs text-muted-foreground">{t('aiAsistan.genel.aciklama')}</p>
          <div className="grid gap-4 md:grid-cols-3">
            <Alan etiket={t('aiAsistan.genel.model')} ipucu={t('aiAsistan.genel.modelIpucu', { model: a.model })}>
              <Input value={a.model_ayari} onChange={(e) => setA({ ...a, model_ayari: e.target.value })} placeholder={a.model} dir="ltr" />
            </Alan>
            <Alan etiket={t('aiAsistan.genel.gunlukButce')} ipucu={t('aiAsistan.genel.gunlukButceIpucu')}>
              <Input type="number" min={0} value={a.gunluk_butce} onChange={(e) => setA({ ...a, gunluk_butce: Number(e.target.value) })} />
            </Alan>
            <Alan etiket={t('aiAsistan.genel.ajansGunluk')}>
              <Input type="number" min={0} value={a.ajans_gunluk} onChange={(e) => setA({ ...a, ajans_gunluk: Number(e.target.value) })} />
            </Alan>
            <Alan etiket={t('aiAsistan.genel.blokMesaj')}>
              <Input type="number" min={1} value={a.blok_mesaj} onChange={(e) => setA({ ...a, blok_mesaj: Number(e.target.value) })} />
            </Alan>
            <Alan etiket={t('aiAsistan.genel.blokKredi')} ipucu={t('aiAsistan.genel.blokKrediIpucu')}>
              <Input type="number" min={0} step={0.25} value={a.blok_kredi} onChange={(e) => setA({ ...a, blok_kredi: Number(e.target.value) })} />
            </Alan>
            <Alan etiket={t('aiAsistan.genel.gommeModeli')} ipucu={t(a.gomme_hazir ? 'aiAsistan.genel.gommeHazir' : 'aiAsistan.genel.gommeYok')}>
              <Input value={a.gomme_modeli} onChange={(e) => setA({ ...a, gomme_modeli: e.target.value })} dir="ltr" />
            </Alan>
          </div>
          <Button type="button" onClick={() => void kaydet()} disabled={kaydediliyor} className="gap-1.5">
            {kaydediliyor && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('aiAsistan.kaydet')}
          </Button>
        </div>
      )}
    </div>
  );
}
