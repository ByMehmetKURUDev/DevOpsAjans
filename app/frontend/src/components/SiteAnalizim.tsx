import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Copy, Loader2, Search, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import SiteRaporGorunumu from '@/components/SiteRaporGorunumu';
import { kendiSitelerim, type MusteriSitesi } from '@/lib/musteriSiteleri';
import {
  SiteAnaliziHatasi,
  benimAnalizim,
  benimListem,
  benimRaporum,
  puanRengi,
  raporAdresi,
  type AnalizSatiri,
  type TamRapor,
} from '@/lib/siteAnalizi';

/**
 * Müşteri paneli › Analiz.
 *
 * Müşteri kendi sitesini (ya da herhangi bir siteyi) analiz ediyor; tam
 * rapor e-posta istemeden doğrudan açılıyor — kim olduğu zaten oturumdan
 * belli. Bakımını yaptığımız siteler (`musteri_siteleri`) hızlı seçim
 * olarak öneriliyor. Günde 10 analiz sınırı var.
 */

function tarih(deger: string | null | undefined, dil: string): string {
  if (!deger) return '—';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '—';
  return an.toLocaleDateString(dil, { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function SiteAnalizim() {
  const { t, i18n } = useTranslation();
  const [adres, setAdres] = useState('');
  const [siteler, setSiteler] = useState<MusteriSitesi[]>([]);
  const [gecmis, setGecmis] = useState<AnalizSatiri[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [calisiyor, setCalisiyor] = useState(false);
  const [acik, setAcik] = useState<TamRapor | null>(null);
  const [aciliyor, setAciliyor] = useState<number | null>(null);

  const hataGoster = (hata: unknown) => {
    const kod = hata instanceof SiteAnaliziHatasi ? hata.kod : 'genel';
    toast.error(t(`siteAnalizi.hata.${kod}`, { defaultValue: t('siteAnalizi.hata.genel') }));
  };

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const [liste, kayitli] = await Promise.all([
        benimListem(),
        kendiSitelerim().catch(() => [] as MusteriSitesi[]),
      ]);
      setGecmis(liste);
      setSiteler(kayitli.filter((s) => Boolean(s.adres)));
    } catch {
      toast.error(t('siteAnalizi.hata.genel'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const analizEt = async (olay?: FormEvent, hedef?: string) => {
    olay?.preventDefault();
    const url = (hedef ?? adres).trim();
    if (!url || calisiyor) return;
    setCalisiyor(true);
    try {
      const rapor = await benimAnalizim(url);
      setAcik(rapor);
      void benimListem().then(setGecmis).catch(() => undefined);
    } catch (hata) {
      hataGoster(hata);
    } finally {
      setCalisiyor(false);
    }
  };

  const ac = async (id: number) => {
    setAciliyor(id);
    try {
      setAcik(await benimRaporum(id));
    } catch (hata) {
      hataGoster(hata);
    } finally {
      setAciliyor(null);
    }
  };

  const baglantiKopyala = async (jeton: string) => {
    try {
      await navigator.clipboard.writeText(raporAdresi(jeton));
      toast.success(t('siteAnalizi.musteri.kopyalandi'));
    } catch {
      toast.error(t('siteAnalizi.hata.genel'));
    }
  };

  if (acik) {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap justify-end gap-2">
          {acik.jeton && acik.durum === 'tamam' ? (
            <Button variant="outline" onClick={() => void baglantiKopyala(acik.jeton!)} className="gap-2">
              <Copy className="h-4 w-4" aria-hidden="true" />
              {t('siteAnalizi.musteri.paylas')}
            </Button>
          ) : null}
          <Button variant="outline" onClick={() => setAcik(null)} className="gap-2">
            <X className="h-4 w-4" aria-hidden="true" />
            {t('siteAnalizi.musteri.kapat')}
          </Button>
        </div>
        {acik.durum === 'tamam' ? (
          <SiteRaporGorunumu rapor={acik} yazdirilabilir />
        ) : (
          <p className="rounded-xl border border-white/10 p-6 text-sm text-muted-foreground">
            {t(`siteAnalizi.hata.${acik.hata_kodu || 'genel'}`, { defaultValue: t('siteAnalizi.hata.genel') })}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={(o) => void analizEt(o)}
        className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      >
        <h3 className="text-lg font-semibold">{t('siteAnalizi.musteri.baslik')}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{t('siteAnalizi.musteri.aciklama')}</p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <input
            value={adres}
            onChange={(o) => setAdres(o.target.value)}
            placeholder={t('siteAnalizi.adresOrnek')}
            inputMode="url"
            spellCheck={false}
            disabled={calisiyor}
            aria-label={t('siteAnalizi.adresEtiketi')}
            className="h-11 w-full rounded-lg border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus:border-primary focus:outline-none"
          />
          <Button type="submit" disabled={calisiyor || !adres.trim()} className="h-11 gap-2 sm:flex-none">
            {calisiyor ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Search className="h-4 w-4" aria-hidden="true" />
            )}
            {calisiyor ? t('siteAnalizi.calisiyor') : t('siteAnalizi.musteri.analizEt')}
          </Button>
        </div>
        {siteler.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-xs text-muted-foreground">{t('siteAnalizi.musteri.sitelerim')}</p>
            <div className="flex flex-wrap gap-2">
              {siteler.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  disabled={calisiyor}
                  onClick={() => {
                    setAdres(s.adres || '');
                    void analizEt(undefined, s.adres || '');
                  }}
                  className="rounded-full border border-white/10 px-3 py-1 text-xs hover:bg-white/5 disabled:opacity-50"
                >
                  {s.ad} · {s.adres}
                </button>
              ))}
            </div>
          </div>
        )}
        {calisiyor && <p className="mt-3 text-xs text-muted-foreground">{t('siteAnalizi.bekleyin')}</p>}
      </form>

      <div className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <h3 className="mb-4 text-lg font-semibold">{t('siteAnalizi.musteri.gecmis')}</h3>
        {yukleniyor ? (
          <div className="flex justify-center py-6 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : gecmis.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('siteAnalizi.musteri.bos')}</p>
        ) : (
          <ul className="divide-y divide-white/5">
            {gecmis.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="break-all font-medium">{s.alan_adi}</p>
                  <p className="text-xs text-muted-foreground">{tarih(s.created_at, i18n.language)}</p>
                </div>
                <div className="flex items-center gap-4">
                  <span className={`text-lg font-bold ${puanRengi(s.puan)}`}>
                    {s.durum === 'tamam' ? (s.puan ?? '—') : '—'}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={aciliyor === s.id}
                    onClick={() => void ac(s.id)}
                  >
                    {aciliyor === s.id ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" /> : null}
                    {t('siteAnalizi.musteri.ac')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
