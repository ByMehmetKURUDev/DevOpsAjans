import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, FileText, FolderOpen, Inbox, Loader2, RefreshCw, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DosyaHatasi,
  adresiIndir,
  boyutBicimle,
  dosyalarim,
  istenenBelgeler,
  musteriIndirmeAdresi,
  musteriYukle,
  talebeYukle,
  tarihBicimle,
  type BelgeTalebi,
  type MusteriDosyalari,
} from '@/lib/dosyalar';

/**
 * Müşteri paneli › Dosyalar (Faz 2C).
 *
 * Üstte "İstenen belgeler" (ajansın istediği belgeler, son tarih, yükle),
 * altta müşteriye görünür klasörler ve dosyalar. İndirme her zaman sunucudan
 * alınan 15 dakikalık imzalı adresle; ekip klasörleri burada hiç görünmüyor.
 */

const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6';

export default function Dosyalarim() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<MusteriDosyalari | null>(null);
  const [talepler, setTalepler] = useState<BelgeTalebi[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [calisan, setCalisan] = useState<string | null>(null);
  const [acikKlasor, setAcikKlasor] = useState<string | null>(null);

  const hata = useCallback(
    (h: unknown) => {
      const kod = h instanceof DosyaHatasi ? h.kod : 'genel';
      const ek = h instanceof DosyaHatasi ? h.ek : {};
      toast.error(t(`dosyalar.hata.${kod}`, { defaultValue: t('dosyalar.hata.genel'), ...ek }));
    },
    [t]
  );

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const [v, bt] = await Promise.all([dosyalarim(), istenenBelgeler()]);
      setVeri(v);
      setTalepler(bt);
    } catch (h) {
      hata(h);
    } finally {
      setYukleniyor(false);
    }
  }, [hata]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const gruplar = useMemo(() => {
    const m = new Map<string, MusteriDosyalari['dosyalar']>();
    for (const k of veri?.klasorler ?? []) m.set(k, []);
    for (const d of veri?.dosyalar ?? []) {
      if (!m.has(d.klasor)) m.set(d.klasor, []);
      m.get(d.klasor)!.push(d);
    }
    return [...m.entries()];
  }, [veri]);

  const indir = async (id: number) => {
    try {
      adresiIndir((await musteriIndirmeAdresi(id)).adres);
    } catch (h) {
      hata(h);
    }
  };

  const dosyaYukle = async (dosya: File | undefined, talepId?: number) => {
    if (!dosya) return;
    setCalisan(talepId ? `talep-${talepId}` : 'genel');
    try {
      if (talepId) await talebeYukle(talepId, dosya);
      else await musteriYukle(dosya);
      toast.success(t('dosyalar.yuklendi', { ad: dosya.name }));
      await yukle();
    } catch (h) {
      hata(h);
    } finally {
      setCalisan(null);
    }
  };

  if (yukleniyor && !veri) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
      </div>
    );
  }

  const bekleyen = talepler.filter((x) => x.durum === 'bekliyor');

  return (
    <div className="space-y-6" data-testid="dosyalarim">
      <div className={KART}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Inbox className="h-5 w-5 text-amber-300" aria-hidden="true" />
            {t('dosyalar.istenen.baslik')}
            {bekleyen.length > 0 && (
              <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-100">{bekleyen.length}</span>
            )}
          </h3>
          <Button size="sm" variant="ghost" className="gap-2" onClick={() => void yukle()}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
            {t('dosyalar.yenile')}
          </Button>
        </div>
        {talepler.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('dosyalar.istenen.bos')}</p>
        ) : (
          <ul className="space-y-3">
            {talepler.map((bt) => {
              const gecikti = bt.durum === 'bekliyor' && bt.kalan_gun !== null && bt.kalan_gun < 0;
              return (
                <li key={bt.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-4" data-testid={`istenen-${bt.id}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{bt.baslik}</p>
                      {bt.aciklama && <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">{bt.aciklama}</p>}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {bt.son_tarih
                          ? `${t('dosyalar.talep.sonTarih')}: ${tarihBicimle(bt.son_tarih, dil)}`
                          : t('dosyalar.talep.sonTarihYok')}
                        {bt.kabul_turleri.length ? ` · ${t('dosyalar.istenen.turler')}: ${bt.kabul_turleri.join(', ')}` : ''}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[11px] ${
                        bt.durum === 'teslim_edildi'
                          ? 'bg-emerald-500/15 text-emerald-200'
                          : gecikti
                            ? 'bg-red-500/15 text-red-200'
                            : 'bg-amber-500/15 text-amber-200'
                      }`}
                    >
                      {gecikti ? t('dosyalar.talep.durum.gecikti') : t(`dosyalar.talep.durum.${bt.durum}`)}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-white/15 bg-white/5 px-3 py-1.5 text-sm hover:border-white/30">
                      {calisan === `talep-${bt.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                      {bt.durum === 'teslim_edildi' ? t('dosyalar.istenen.yeniSurum') : t('dosyalar.istenen.yukle')}
                      <input
                        type="file"
                        className="sr-only"
                        accept={bt.kabul_turleri.length ? bt.kabul_turleri.map((u) => `.${u}`).join(',') : undefined}
                        disabled={calisan !== null}
                        onChange={(e) => {
                          void dosyaYukle(e.target.files?.[0], bt.id);
                          e.target.value = '';
                        }}
                        data-testid={`istenen-yukle-${bt.id}`}
                      />
                    </label>
                    {bt.dosya && (
                      <button type="button" className="text-xs text-purple-300 hover:text-purple-200" onClick={() => void indir(bt.dosya!.id)}>
                        {bt.dosya.ad} · {tarihBicimle(bt.teslim_at, dil, true)}
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className={KART}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <FolderOpen className="h-5 w-5 text-purple-300" aria-hidden="true" />
            {t('dosyalar.musteri.baslik')}
          </h3>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-gradient-to-r from-purple-600 to-pink-600 px-4 py-2 text-sm text-white">
            {calisan === 'genel' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {t('dosyalar.yukle')}
            <input
              type="file"
              className="sr-only"
              disabled={calisan !== null}
              onChange={(e) => {
                void dosyaYukle(e.target.files?.[0]);
                e.target.value = '';
              }}
              data-testid="musteri-dosya-yukle"
            />
          </label>
        </div>
        <p className="mb-4 text-xs text-muted-foreground">
          {t('dosyalar.kurallar', { sayi: veri?.boyut_siniri_mb ?? 20, turler: (veri?.izinli_turler ?? []).join(', ') })}
        </p>
        {gruplar.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('dosyalar.bos')}</p>
        ) : (
          <div className="space-y-3">
            {gruplar.map(([ad, liste]) => {
              const acik = acikKlasor === null || acikKlasor === ad;
              return (
                <div key={ad} className="rounded-xl border border-white/10">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-2 px-4 py-2 text-left text-sm font-medium"
                    onClick={() => setAcikKlasor(acikKlasor === ad ? null : ad)}
                    aria-expanded={acik}
                  >
                    <span className="flex items-center gap-2">
                      <FolderOpen className="h-4 w-4 text-amber-300" aria-hidden="true" /> {ad}
                    </span>
                    <span className="text-xs text-muted-foreground">{liste.length}</span>
                  </button>
                  {acik && liste.length > 0 && (
                    <ul className="divide-y divide-white/5 border-t border-white/10">
                      {liste.map((d) => (
                        <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm" data-testid={`musteri-dosya-${d.id}`}>
                          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                          <span className="min-w-0 flex-1">
                            <span className="block break-words">{d.ad}</span>
                            <span className="block text-xs text-muted-foreground">
                              {boyutBicimle(d.boyut, dil)} · {tarihBicimle(d.created_at, dil)}
                            </span>
                          </span>
                          <Button size="sm" variant="ghost" className="gap-1" onClick={() => void indir(d.id)}>
                            <Download className="h-4 w-4" /> {t('dosyalar.indir')}
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
