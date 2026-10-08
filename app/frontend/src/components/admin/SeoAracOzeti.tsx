import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, Loader2, RefreshCw, Wrench } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { seoAracOzeti } from '@/lib/siteAnalizi';
import type { AracYonetimOzeti } from '@/lib/seoAraclari';
import { SEO_ARACLARI, seoAraclariYolu } from '../../../prerender/seo-araclari-veri.js';

/**
 * Yönetici paneli › Satış › Site analizleri › "Ücretsiz SEO araçları" (Faz 4S).
 *
 * Yeni üst sekme DEĞİL: Site analizleri bölümünün içinde küçük bir alt görünüm.
 * Son 30 günde araç başına günlük çalıştırma (küçük çubuklar, kütüphanesiz),
 * hatalı biten, "Sonucu e-postayla gönder" sayısı ve bunlardan açılan YENİ CRM
 * adayı (dönüşüm = e-posta / kullanım) ve "Sitenin tam analizini al" geçişleri
 * (başlatılan / e-posta bırakılan). Sorgulanan adresler saklanmadığı için liste YOK.
 */
const GUN = 30;

function yuzde(pay: number, payda: number): string {
  if (!payda) return '—';
  return `%${Math.round((pay / payda) * 1000) / 10}`;
}

function GunlukCubuklar({ degerler, gunler, ipucu }: { degerler: number[]; gunler: string[]; ipucu: (gun: string, sayi: number) => string }) {
  const enBuyuk = Math.max(1, ...degerler);
  return (
    <div className="flex h-6 w-[120px] items-end gap-px" aria-hidden="true" data-gunluk-cubuk>
      {degerler.map((d, i) => (
        <span
          key={gunler[i] ?? i}
          title={ipucu(gunler[i] ?? '', d)}
          className={`w-full rounded-sm ${d ? 'bg-purple-400/70' : 'bg-white/10'}`}
          style={{ height: `${d ? Math.max(12, Math.round((d / enBuyuk) * 100)) : 8}%` }}
        />
      ))}
    </div>
  );
}

export default function SeoAracOzeti() {
  const { t, i18n } = useTranslation();
  const [ozet, setOzet] = useState<AracYonetimOzeti | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      setOzet(await seoAracOzeti(GUN));
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const adi = (slug: string) => {
    const a = SEO_ARACLARI.find((x) => x.slug === slug);
    return a ? t(`seoAraclari.arac.${a.anahtar}.ad`) : slug;
  };
  const gunAdi = (gun: string) => {
    const an = new Date(`${gun}T12:00:00Z`);
    return Number.isNaN(an.getTime()) ? gun : an.toLocaleDateString(i18n.language, { day: 'numeric', month: 'short' });
  };
  const ipucu = (gun: string, sayi: number) => t('seoAraclari.yonetim.gunIpucu', { gun: gunAdi(gun), sayi });
  const kutucuk = (ad: string, deger: number | string, testId: string, alt?: string) => (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3" data-testid={testId}>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{ad}</p>
      <p className="mt-1 text-xl font-semibold">{deger}</p>
      {alt && <p className="mt-0.5 text-[11px] text-muted-foreground">{alt}</p>}
    </div>
  );

  return (
    <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6" data-testid="seo-arac-ozeti">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Wrench className="h-5 w-5 text-purple-300" aria-hidden="true" />
            {t('seoAraclari.yonetim.baslik')}
          </h3>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">{t('seoAraclari.yonetim.aciklama', { gun: GUN })}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <a href={seoAraclariYolu('tr')} target="_blank" rel="noopener">
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              {t('seoAraclari.yonetim.sayfayiAc')}
            </a>
          </Button>
          <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('seoAraclari.yonetim.baslik')}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          </Button>
        </div>
      </div>

      {hata && !ozet ? (
        <p className="text-sm text-red-300">{t('seoAraclari.yonetim.hataYukle')}</p>
      ) : !ozet ? (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {kutucuk(t('seoAraclari.yonetim.toplamKullanim'), ozet.toplam.kullanim, 'seo-arac-toplam')}
            {kutucuk(
              t('seoAraclari.yonetim.toplamEposta'),
              ozet.toplam.eposta,
              'seo-arac-eposta',
              `${t('seoAraclari.yonetim.donusum')}: ${yuzde(ozet.toplam.eposta, ozet.toplam.kullanim)}`,
            )}
            {kutucuk(t('seoAraclari.yonetim.toplamAday'), ozet.toplam.aday, 'seo-arac-aday')}
            {kutucuk(
              t('seoAraclari.yonetim.toplamTamAnaliz'),
              ozet.toplam.tam_analiz,
              'seo-arac-tam-analiz',
              t('seoAraclari.yonetim.tamAnalizAlt', { sayi: ozet.toplam.tam_analiz_aday }),
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-start text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b border-white/10">
                  <th className="py-2 pe-4 text-start font-medium">{t('seoAraclari.yonetim.arac')}</th>
                  <th className="py-2 pe-4 text-start font-medium">{t('seoAraclari.yonetim.gunluk')}</th>
                  <th className="py-2 pe-4 text-end font-medium">{t('seoAraclari.yonetim.kullanim')}</th>
                  <th className="py-2 pe-4 text-end font-medium">{t('seoAraclari.yonetim.hata')}</th>
                  <th className="py-2 pe-4 text-end font-medium">{t('seoAraclari.yonetim.eposta')}</th>
                  <th className="py-2 pe-4 text-end font-medium">{t('seoAraclari.yonetim.aday')}</th>
                  <th className="py-2 pe-4 text-end font-medium" title={t('seoAraclari.yonetim.donusumIpucu')}>
                    {t('seoAraclari.yonetim.donusum')}
                  </th>
                  <th className="py-2 text-end font-medium">{t('seoAraclari.yonetim.tamAnaliz')}</th>
                </tr>
              </thead>
              <tbody>
                {ozet.araclar.map((s) => (
                  <tr key={s.arac} className="border-b border-white/5" data-testid={`seo-arac-satir-${s.arac}`}>
                    <td className="py-2 pe-4">{adi(s.arac)}</td>
                    <td className="py-2 pe-4">
                      <GunlukCubuklar degerler={s.gunluk} gunler={ozet.gunler} ipucu={ipucu} />
                    </td>
                    <td className="py-2 pe-4 text-end font-semibold">{s.kullanim}</td>
                    <td className="py-2 pe-4 text-end text-muted-foreground">{s.hata}</td>
                    <td className="py-2 pe-4 text-end">{s.eposta}</td>
                    <td className="py-2 pe-4 text-end">{s.aday}</td>
                    <td className="py-2 pe-4 text-end text-muted-foreground">{yuzde(s.eposta, s.kullanim)}</td>
                    <td className="py-2 text-end">
                      {s.tam_analiz}
                      {s.tam_analiz_aday > 0 && <span className="text-xs text-muted-foreground"> / {s.tam_analiz_aday}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="text-xs font-semibold">
                  <td className="py-2 pe-4">{t('seoAraclari.yonetim.toplam')}</td>
                  <td className="py-2 pe-4">
                    <GunlukCubuklar degerler={ozet.gunluk} gunler={ozet.gunler} ipucu={ipucu} />
                  </td>
                  <td className="py-2 pe-4 text-end">{ozet.toplam.kullanim}</td>
                  <td className="py-2 pe-4 text-end text-muted-foreground">{ozet.toplam.hata}</td>
                  <td className="py-2 pe-4 text-end">{ozet.toplam.eposta}</td>
                  <td className="py-2 pe-4 text-end">{ozet.toplam.aday}</td>
                  <td className="py-2 pe-4 text-end text-muted-foreground">{yuzde(ozet.toplam.eposta, ozet.toplam.kullanim)}</td>
                  <td className="py-2 text-end">
                    {ozet.toplam.tam_analiz}
                    {ozet.toplam.tam_analiz_aday > 0 && <span className="text-muted-foreground"> / {ozet.toplam.tam_analiz_aday}</span>}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
