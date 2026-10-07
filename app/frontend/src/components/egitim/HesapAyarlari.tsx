import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Loader2, Save, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Alan, Anahtar, KART, METIN_ALANI, Rozet, Yukleniyor } from '@/components/randevu/ortak';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { hataMetni, type EgitimApi, type HesapAyari, type Meta } from '@/lib/egitim';

/**
 * Faz 6K — eğitim ayarları (hesap düzeyi): sertifikada görünen kurum adı + imza, herkese açık kurs listesi
 * sayfası (`/egitim/kurum/<adres>`), kullanım sınırları ve AI soru üretimi hakkı.
 */

export default function HesapAyarlari({ api, meta }: { api: EgitimApi; meta: Meta }) {
  const { t } = useTranslation();
  const [a, setA] = useState<HesapAyari | null>(null);
  const [mesgul, setMesgul] = useState(false);

  useEffect(() => {
    let iptal = false;
    api
      .ayarlar()
      .then((x) => {
        if (!iptal) setA(x);
      })
      .catch((e) => toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, t]);

  if (!a) return <Yukleniyor />;

  const kaydet = async () => {
    setMesgul(true);
    try {
      setA(
        await api.ayarlarYaz({
          kurum_adi: a.kurum_adi, imza_adi: a.imza_adi, imza_unvan: a.imza_unvan, liste_slug: a.liste_slug,
          liste_baslik: a.liste_baslik, liste_aciklama: a.liste_aciklama, liste_acik: a.liste_acik,
        })
      );
      toast.success(t('egitim.kaydedildi'));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  const ai = meta.ai;
  return (
    <div className="grid gap-4" data-testid="egitim-hesap-ayarlari">
      <div className={`${KART} grid gap-3 p-4 sm:p-6 md:grid-cols-3`}>
        <h4 className="text-base font-semibold md:col-span-3">{t('egitim.ayar.sertifikaBaslik')}</h4>
        <Alan etiket={t('egitim.ayar.kurumAdi')} ipucu={t('egitim.ayar.kurumAdiIpucu')}>
          <Input value={a.kurum_adi} onChange={(e) => setA({ ...a, kurum_adi: e.target.value })} maxLength={160} data-testid="egitim-ayar-kurum" />
        </Alan>
        <Alan etiket={t('egitim.ayar.imzaAdi')}>
          <Input value={a.imza_adi} onChange={(e) => setA({ ...a, imza_adi: e.target.value })} maxLength={120} />
        </Alan>
        <Alan etiket={t('egitim.ayar.imzaUnvan')}>
          <Input value={a.imza_unvan} onChange={(e) => setA({ ...a, imza_unvan: e.target.value })} maxLength={120} />
        </Alan>
      </div>

      <div className={`${KART} grid gap-3 p-4 sm:p-6 md:grid-cols-2`}>
        <div className="md:col-span-2">
          <h4 className="text-base font-semibold">{t('egitim.ayar.listeBaslik')}</h4>
          <p className="mt-1 text-sm text-muted-foreground">{t('egitim.ayar.listeAciklama')}</p>
        </div>
        <Alan etiket={t('egitim.ayar.listeSlug')} ipucu={`${meta.adres_tabani}kurum/${a.liste_slug || '…'}`}>
          <Input value={a.liste_slug} onChange={(e) => setA({ ...a, liste_slug: e.target.value.toLowerCase() })} maxLength={60} dir="ltr" placeholder="akademi" />
        </Alan>
        <Alan etiket={t('egitim.ayar.listeBasligi')}>
          <Input value={a.liste_baslik} onChange={(e) => setA({ ...a, liste_baslik: e.target.value })} maxLength={160} />
        </Alan>
        <Alan etiket={t('egitim.ayar.listeMetni')} className="md:col-span-2">
          <textarea value={a.liste_aciklama} onChange={(e) => setA({ ...a, liste_aciklama: e.target.value })} rows={3} maxLength={1000} className={METIN_ALANI} />
        </Alan>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          <Anahtar acik={a.liste_acik} onDegis={(v) => setA({ ...a, liste_acik: v })} etiket={t('egitim.ayar.listeAcik')} />
          {a.liste_acik && a.liste_slug && (
            <a href={`/egitim/kurum/${a.liste_slug}`} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-sm text-blue-200 hover:underline">
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              {t('egitim.ac')}
            </a>
          )}
        </div>
      </div>

      <div className="flex justify-end">
        <Button onClick={() => void kaydet()} disabled={mesgul} className="gap-1.5" data-testid="egitim-ayar-kaydet">
          {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />}
          {t('egitim.kaydet')}
        </Button>
      </div>

      <div className={`${KART} grid gap-3 p-4 sm:p-6`}>
        <h4 className="text-base font-semibold">{t('egitim.ayar.kullanimBaslik')}</h4>
        <div className="flex flex-wrap gap-2 text-sm">
          <Rozet>
            {meta.kurs_siniri != null
              ? t('egitim.ayar.kursKullanim', { sayi: meta.kurs_sayisi ?? 0, sinir: meta.kurs_siniri })
              : t('egitim.ayar.sinirsizKurs')}
          </Rozet>
          <Rozet>
            {meta.ogrenci_siniri != null
              ? t('egitim.ayar.ogrenciKullanim', { sayi: meta.ogrenci_sayisi ?? 0, sinir: meta.ogrenci_siniri })
              : t('egitim.ayar.sinirsizOgrenci')}
          </Rozet>
        </div>
        {ai && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground" data-testid="egitim-ayar-ai">
            <Sparkles className="h-4 w-4 text-blue-300" aria-hidden="true" />
            {!ai.hazir
              ? t('egitim.ai.kapali')
              : ai.hak != null
                ? t('egitim.ai.hak', { kullanilan: ai.kullanilan, hak: ai.hak })
                : t('egitim.ai.sinirsiz', { kullanilan: ai.kullanilan })}
          </div>
        )}
        <p className="text-xs text-muted-foreground">{t('egitim.ayar.kvkk')}</p>
      </div>
    </div>
  );
}
