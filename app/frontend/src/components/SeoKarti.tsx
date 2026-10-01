import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Gauge,
  Info,
  Loader2,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import SeoCizgiGrafigi from '@/components/SeoCizgiGrafigi';
import { Button } from '@/components/ui/button';
import {
  CWV_RENGI,
  cwvDurumu,
  musteriSeoGecmisi,
  musteriSeoTara,
  puanRengi,
  sayiBicimle,
  SeoHatasi,
  sureBicimle,
  tarihBicimle,
  yoneticiSeoGecmisi,
  yoneticiSeoTara,
  type SeoBulgu,
  type SeoGecmisi,
} from '@/lib/seoIzleme';

/**
 * Bir sitenin "SEO ve hız" kartı (Faz 2H) — müşteri "Sitem" sekmesinde ve
 * yönetici SEO özetinde satır açılınca aynı görünüm.
 *
 * Son puanlar (genel, mobil, masaüstü), Core Web Vitals (Google eşikleriyle
 * iyi/orta/kötü renkleri), son 90 günün çizgisi, en önemli 5 bulgu ve
 * "Şimdi tara". Bulgu cümleleri site analizi ek paketinden
 * (`siteAnalizi.bulgu.<kod>`); kart onu ve `seoIzleme`yi birlikte yükleyen
 * tembel sarmalayıcılarla açılıyor.
 */
const GUN = 90;

const SEVIYE: Record<string, { renk: string; Ikon: typeof Info }> = {
  hata: { renk: 'text-red-300', Ikon: XCircle },
  uyari: { renk: 'text-amber-300', Ikon: AlertTriangle },
  bilgi: { renk: 'text-sky-300', Ikon: Info },
  iyi: { renk: 'text-emerald-300', Ikon: CheckCircle2 },
};

function Kutu({ etiket, puan, testId, ek }: { etiket: string; puan: number | null; testId: string; ek?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <p className="truncate text-[11px] uppercase tracking-wider text-muted-foreground">{etiket}</p>
      <p className={`mt-1 text-2xl font-bold leading-none ${puanRengi(puan)}`} data-testid={testId}>
        {puan ?? '—'}
      </p>
      {puan === null ? <p className="mt-1 text-[11px] text-muted-foreground">{t('seoIzleme.olculemedi')}</p> : ek}
    </div>
  );
}

function BulguSatiri({ b }: { b: SeoBulgu }) {
  const { t } = useTranslation();
  const bicim = SEVIYE[b.seviye] ?? SEVIYE.bilgi;
  const Ikon = bicim.Ikon;
  const deger = { deger: b.deger ?? '' };
  return (
    <li className="flex items-start gap-2 text-sm leading-snug" data-kod={b.kod}>
      <Ikon className={`mt-0.5 h-4 w-4 flex-none ${bicim.renk}`} aria-hidden="true" />
      <details className="min-w-0 flex-1">
        <summary className="cursor-pointer list-none">
          <span className="font-medium">{t(`siteAnalizi.bulgu.${b.kod}.baslik`, { ...deger, defaultValue: b.kod })}</span>
          {b.kritik && (
            <span className="ms-2 inline-block rounded-full border border-red-400/40 bg-red-500/10 px-1.5 py-px align-middle text-[10px] font-semibold text-red-300">
              {t('seoIzleme.bulgular.kritik')}
            </span>
          )}
        </summary>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {t(`siteAnalizi.bulgu.${b.kod}.oneri`, { ...deger, defaultValue: '' })}
        </p>
      </details>
    </li>
  );
}

export default function SeoKarti({ siteId, yonetici = false }: { siteId: number; yonetici?: boolean }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [veri, setVeri] = useState<SeoGecmisi | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [taraniyor, setTaraniyor] = useState(false);

  const yukle = useCallback(async () => {
    try {
      setVeri(await (yonetici ? yoneticiSeoGecmisi : musteriSeoGecmisi)(siteId, GUN));
      setHata(false);
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, [siteId, yonetici]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const tara = async () => {
    setTaraniyor(true);
    try {
      await (yonetici ? yoneticiSeoTara : musteriSeoTara)(siteId);
      toast.success(t('seoIzleme.tara.tamam'));
    } catch (h) {
      const e = h instanceof SeoHatasi ? h : null;
      if (e?.kod === 'gunluk_sinir') {
        toast.error(t('seoIzleme.tara.gunlukSinir', { tarih: tarihBicimle(String(e.ek.sonraki_at ?? ''), dil, true) }));
      } else if (e?.kod === 'tarama_suruyor') {
        toast.error(t('seoIzleme.tara.suruyorHata'));
      } else if (e?.kod === 'adres_yok') {
        toast.error(t('seoIzleme.tara.adresYok'));
      } else {
        toast.error(t('seoIzleme.tara.hata'));
      }
    } finally {
      setTaraniyor(false);
      await yukle();
    }
  };

  const son = veri?.son ?? null;
  const deneme = veri?.son_deneme ?? null;
  const sonHata =
    deneme && deneme.durum === 'hata' && (!son || (deneme.olcum_at ?? '') > (son.olcum_at ?? '')) ? deneme : null;
  const elleKapali = !yonetici && veri?.elle && veri.elle.kalan === 0;
  const mesgul = taraniyor || Boolean(veri?.calisiyor);

  const cwv = son
    ? ([
        ['lcp', son.lcp_ms, sureBicimle(son.lcp_ms, dil)],
        ['cls', son.cls, sayiBicimle(son.cls, dil, 3)],
        ['tbt', son.tbt_ms, sureBicimle(son.tbt_ms, dil)],
      ] as const)
    : [];

  return (
    <section className="space-y-4" data-testid={`seo-karti-${siteId}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <Gauge className="h-4 w-4 text-cyan-300" aria-hidden="true" />
            {t('seoIzleme.baslik')}
          </h4>
          {!yonetici && <p className="mt-1 text-xs text-muted-foreground">{t('seoIzleme.aciklama')}</p>}
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void tara()}
            disabled={mesgul || Boolean(elleKapali) || yukleniyor}
            data-testid={`seo-tara-${siteId}`}
          >
            {mesgul ? <Loader2 className="me-2 h-4 w-4 animate-spin" /> : <RefreshCw className="me-2 h-4 w-4" />}
            {mesgul ? t('seoIzleme.tara.suruyor') : t('seoIzleme.tara.dugme')}
          </Button>
          {elleKapali && veri?.elle.sonraki_at && (
            <p className="max-w-[16rem] text-end text-[11px] text-muted-foreground" data-testid={`seo-sinir-${siteId}`}>
              {t('seoIzleme.tara.gunlukSinir', { tarih: tarihBicimle(veri.elle.sonraki_at, dil, true) })}
            </p>
          )}
        </div>
      </div>

      {yukleniyor ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      ) : hata || !veri ? (
        <p className="text-xs text-red-300">{t('seoIzleme.hata.yuklenemedi')}</p>
      ) : (
        <>
          {sonHata && (
            <p className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200" data-testid={`seo-son-hata-${siteId}`}>
              {t('seoIzleme.sonDenemeHata', {
                sebep: t(`seoIzleme.hataKodu.${sonHata.hata_kodu ?? 'beklenmedik'}`, {
                  defaultValue: t('seoIzleme.hataKodu.beklenmedik'),
                }),
              })}
            </p>
          )}
          {!son ? (
            <p className="text-sm text-muted-foreground" data-testid={`seo-bos-${siteId}`}>
              {t('seoIzleme.henuzYok')}
            </p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2">
                <Kutu
                  etiket={t('seoIzleme.genel')}
                  puan={son.genel_puan}
                  testId={`seo-genel-${siteId}`}
                  ek={
                    veri.degisim !== null && veri.degisim !== 0 ? (
                      <p
                        className={`mt-1 inline-flex items-center gap-0.5 text-[11px] ${veri.degisim > 0 ? 'text-emerald-300' : 'text-red-300'}`}
                        data-testid={`seo-degisim-${siteId}`}
                      >
                        {veri.degisim > 0 ? <ArrowUpRight className="h-3 w-3" aria-hidden="true" /> : <ArrowDownRight className="h-3 w-3" aria-hidden="true" />}
                        {t('seoIzleme.degisim', { sayi: `${veri.degisim > 0 ? '+' : ''}${veri.degisim}` })}
                      </p>
                    ) : undefined
                  }
                />
                <Kutu etiket={t('seoIzleme.mobil')} puan={son.mobil_puan} testId={`seo-mobil-${siteId}`} />
                <Kutu etiket={t('seoIzleme.masaustu')} puan={son.masaustu_puan} testId={`seo-masaustu-${siteId}`} />
              </div>
              <p className="text-[11px] text-muted-foreground">
                {t('seoIzleme.sonOlcum', { tarih: tarihBicimle(son.olcum_at, dil, true) })}
                {' · '}
                {veri.tarama_gun > 0 && veri.sonraki_tarama_at
                  ? t('seoIzleme.sonrakiTarama', { tarih: tarihBicimle(veri.sonraki_tarama_at, dil) })
                  : t('seoIzleme.otomatikKapali')}
              </p>

              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">{t('seoIzleme.cwv.baslik')}</p>
                <div className="grid gap-2 sm:grid-cols-3">
                  {cwv.map(([anahtar, ham, metin]) => {
                    const durum = cwvDurumu(anahtar, ham);
                    return (
                      <div
                        key={anahtar}
                        className={`rounded-xl border px-3 py-2 ${durum ? CWV_RENGI[durum] : 'border-white/10 text-muted-foreground'}`}
                        data-testid={`seo-${anahtar}-${siteId}`}
                        data-durum={durum ?? 'yok'}
                      >
                        <p className="truncate text-[11px] opacity-80">{t(`seoIzleme.cwv.${anahtar}`)}</p>
                        <p className="text-lg font-semibold leading-tight">{metin}</p>
                        <p className="text-[11px]">{durum ? t(`seoIzleme.cwv.${durum}`) : t('seoIzleme.olculemedi')}</p>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-1 text-[10px] text-muted-foreground">{t('seoIzleme.cwv.esik')}</p>
              </div>

              <SeoCizgiGrafigi olcumler={veri.gecmis} gun={veri.gun} testId={`seo-grafik-${siteId}`} />

              <div>
                <p className="mb-2 text-xs font-medium text-muted-foreground">{t('seoIzleme.bulgular.baslik')}</p>
                {son.onemli_bulgular.length === 0 ? (
                  <p className="text-sm text-emerald-300">{t('seoIzleme.bulgular.yok')}</p>
                ) : (
                  <ul className="space-y-2" data-testid={`seo-bulgular-${siteId}`}>
                    {son.onemli_bulgular.map((b, i) => (
                      <BulguSatiri key={`${b.kod}-${i}`} b={b} />
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
          {!yonetici && <p className="text-[11px] text-muted-foreground">{t('seoIzleme.tara.sinirNotu')}</p>}
        </>
      )}
    </section>
  );
}
