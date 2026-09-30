import { useCallback, useEffect, useState } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import BaglantiKutusu from '@/components/admin/BaglantiKutusu';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  IslemHatasi,
  durumRengi,
  islemListesi,
  islemOlustur,
  olumluMu,
  tarihSaatBicimle,
  type OlusturYaniti,
  type YonetimIslemi,
} from '@/lib/imzaliIslem';

/**
 * Proje aşama yöneticisindeki kısa yol: "Müşteri onayı iste".
 *
 * Yönetici paneli › İmzalı işlemler'deki formun teslimat için hazır hali:
 * hedef bu proje, alıcı projenin müşterisi. Aynı uca gidiyor. Altında bu
 * projenin önceki onay istekleri ve sonuçları duruyor.
 */
export default function MusteriOnayiIste({ projectId, clientEmail }: { projectId: number; clientEmail: string }) {
  const { t, i18n } = useTranslation();
  const [acik, setAcik] = useState(false);
  const [not, setNot] = useState('');
  const [baglanti, setBaglanti] = useState('');
  const [eposta, setEposta] = useState(true);
  const [calisiyor, setCalisiyor] = useState(false);
  const [sonuc, setSonuc] = useState<OlusturYaniti | null>(null);
  const [gecmis, setGecmis] = useState<YonetimIslemi[]>([]);

  const yukle = useCallback(async () => {
    try {
      setGecmis(await islemListesi({ tur: 'teslimat_onay', hedef_tablo: 'projects', hedef_id: projectId }));
    } catch {
      setGecmis([]);
    }
  }, [projectId]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const iste = async () => {
    setCalisiyor(true);
    try {
      const yanit = await islemOlustur({
        tur: 'teslimat_onay',
        hedef_id: projectId,
        not: not.trim() || undefined,
        baglanti: baglanti.trim() || undefined,
        eposta_gonder: eposta,
      });
      setSonuc(yanit);
      setAcik(false);
      setNot('');
      setBaglanti('');
      await yukle();
    } catch (h) {
      const kod = h instanceof IslemHatasi ? h.kod : 'genel';
      toast.error(t(`islem.hata.${kod}`, { defaultValue: t('islem.hata.genel') }));
    } finally {
      setCalisiyor(false);
    }
  };

  return (
    <section className="rounded-2xl border border-purple-400/20 bg-purple-500/[0.04] p-5" data-testid="musteri-onayi-iste">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="flex items-center gap-2 font-semibold">
            <ShieldCheck className="h-4 w-4 text-purple-300" aria-hidden="true" />
            {t('islem.kisayol.baslik')}
          </h4>
          <p className="mt-1 text-xs text-muted-foreground">{t('islem.kisayol.aciklama', { eposta: clientEmail })}</p>
        </div>
        {!acik && (
          <Button type="button" size="sm" onClick={() => setAcik(true)} data-testid="musteri-onayi-ac">
            {t('islem.kisayol.dugme')}
          </Button>
        )}
      </div>

      {sonuc && (
        <div className="mt-4">
          <BaglantiKutusu yanit={sonuc} onKapat={() => setSonuc(null)} />
        </div>
      )}

      {acik && (
        <div className="mt-4 grid gap-3">
          <Input
            value={not}
            onChange={(e) => setNot(e.target.value)}
            placeholder={t('islem.kisayol.notYertutucu')}
            maxLength={2000}
            aria-label={t('islem.yonetim.not')}
            name="kisayol-not"
          />
          <Input
            value={baglanti}
            onChange={(e) => setBaglanti(e.target.value)}
            placeholder={t('islem.kisayol.baglantiYertutucu')}
            aria-label={t('islem.yonetim.teslimBaglantisi')}
            name="kisayol-baglanti"
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={eposta}
              onChange={(e) => setEposta(e.target.checked)}
              className="h-4 w-4 accent-purple-500"
            />
            {t('islem.yonetim.epostaGonder')}
          </label>
          <div className="flex gap-2">
            <Button type="button" onClick={() => void iste()} disabled={calisiyor} data-testid="musteri-onayi-gonder">
              {calisiyor && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
              {t('islem.kisayol.gonder')}
            </Button>
            <Button type="button" variant="outline" className="!bg-transparent" onClick={() => setAcik(false)}>
              {t('islem.vazgec')}
            </Button>
          </div>
        </div>
      )}

      {gecmis.length > 0 && (
        <ul className="mt-4 space-y-2 text-xs">
          {gecmis.slice(0, 5).map((g) => (
            <li key={g.id} className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 ${durumRengi(g.durum)}`}>
                {t(`islem.durumAdi.${g.durum}`, { defaultValue: g.durum })}
              </span>
              {g.sonuc && (
                <span className={olumluMu(g.sonuc) ? 'text-emerald-300' : 'text-amber-300'}>
                  {t(`islem.sonuc.${g.sonuc}`)}
                </span>
              )}
              <span className="text-muted-foreground">
                {g.ayrinti?.asama ? t(`panel.asama.${g.ayrinti.asama}.ad`, { defaultValue: g.ayrinti.asama }) : ''} ·{' '}
                {tarihSaatBicimle(g.created_at, i18n.language)}
              </span>
              {g.sonuc_notu && <span className="w-full whitespace-pre-line break-words text-muted-foreground">“{g.sonuc_notu}”</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
