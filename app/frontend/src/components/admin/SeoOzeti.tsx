import { Fragment, useCallback, useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, ChevronDown, ChevronUp, Gauge, Loader2, RefreshCw, TrendingDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import SeoKarti from '@/components/SeoKarti';
import { Button } from '@/components/ui/button';
import { puanRengi, seoAyarKaydet, seoOzeti, tarihBicimle, type SeoOzetSatiri } from '@/lib/seoIzleme';

/**
 * Yönetici › Müşteri siteleri › "SEO ve hız" (Faz 2H, modül #31).
 *
 * Bütün sitelerin son teknik SEO/hız puanı tek tabloda; sunucu sıralıyor:
 * eşik kadar (10) ya da daha çok düşen ya da yeni kritik bulgusu olan siteler
 * en üstte. Satır açılınca o sitenin geçmişi (çizgi, Core Web Vitals, en
 * önemli bulgular, sınırsız "Şimdi tara") aynı `SeoKarti` ile gösteriliyor.
 * Otomatik tarama sıklığı satırdan değişiyor (0 = kapalı).
 */
const SIKLIKLAR = [0, 1, 3, 7, 14, 30];

function Degisim({ deger }: { deger: number | null }) {
  const { t } = useTranslation();
  if (deger === null || deger === 0) return <span className="text-muted-foreground">—</span>;
  const Ikon = deger > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`inline-flex items-center gap-0.5 ${deger > 0 ? 'text-emerald-300' : 'text-red-300'}`}>
      <Ikon className="h-3.5 w-3.5" aria-hidden="true" />
      {t('seoIzleme.degisim', { sayi: `${deger > 0 ? '+' : ''}${deger}` })}
    </span>
  );
}

export default function SeoOzeti() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [satirlar, setSatirlar] = useState<SeoOzetSatiri[]>([]);
  const [esik, setEsik] = useState(10);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [acik, setAcik] = useState<number | null>(null);
  const [kaydedilen, setKaydedilen] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    try {
      const g = await seoOzeti();
      setSatirlar(g.siteler);
      setEsik(g.esik);
    } catch {
      toast.error(t('seoIzleme.hata.yuklenemedi'));
    } finally {
      setYukleniyor(false);
    }
  }, [t]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const siklik = async (s: SeoOzetSatiri, gun: number) => {
    setKaydedilen(s.site_id);
    try {
      await seoAyarKaydet(s.site_id, gun);
      setSatirlar((o) => o.map((x) => (x.site_id === s.site_id ? { ...x, tarama_gun: gun } : x)));
      toast.success(t('seoIzleme.yonetici.ayarKaydedildi'));
    } catch {
      toast.error(t('seoIzleme.hata.genel'));
    } finally {
      setKaydedilen(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="seo-ozeti">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Gauge className="h-4 w-4 text-cyan-300" aria-hidden="true" />
            {t('seoIzleme.yonetici.baslik')}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('seoIzleme.yonetici.aciklama', { esik })}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => void yukle()} disabled={yukleniyor}>
          <RefreshCw className={`me-2 h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} />
          {t('seoIzleme.yonetici.yenile')}
        </Button>
      </div>

      {yukleniyor && satirlar.length === 0 ? (
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      ) : satirlar.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('seoIzleme.yonetici.bos')}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-white/[0.03] text-start text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-start font-medium">{t('seoIzleme.yonetici.site')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('seoIzleme.genel')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('seoIzleme.mobil')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('seoIzleme.masaustu')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('seoIzleme.yonetici.degisim')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('seoIzleme.yonetici.sonOlcum')}</th>
                <th className="px-3 py-2 text-start font-medium">{t('seoIzleme.yonetici.siklik')}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {satirlar.map((s) => (
                <Fragment key={s.site_id}>
                  <tr
                    className={`border-t border-white/10 ${s.dususte ? 'bg-red-500/[0.06]' : ''}`}
                    data-testid={`seo-ozet-satir-${s.site_id}`}
                    data-dususte={s.dususte ? '1' : '0'}
                  >
                    <td className="max-w-[16rem] px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">{s.ad}</span>
                        {s.dususte && (
                          <span
                            className="inline-flex flex-none items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] text-red-300"
                            data-testid={`seo-dususte-${s.site_id}`}
                          >
                            <TrendingDown className="h-3 w-3" aria-hidden="true" />
                            {t('seoIzleme.yonetici.dususte')}
                          </span>
                        )}
                      </div>
                      <p className="truncate text-[11px] text-muted-foreground">{s.client_email}</p>
                    </td>
                    <td className={`px-3 py-2 text-lg font-bold ${puanRengi(s.son?.genel_puan)}`} data-testid={`seo-ozet-puan-${s.site_id}`}>
                      {s.son?.genel_puan ?? '—'}
                    </td>
                    <td className={`px-3 py-2 font-semibold ${puanRengi(s.son?.mobil_puan)}`}>{s.son?.mobil_puan ?? '—'}</td>
                    <td className={`px-3 py-2 font-semibold ${puanRengi(s.son?.masaustu_puan)}`}>{s.son?.masaustu_puan ?? '—'}</td>
                    <td className="px-3 py-2 text-xs">
                      <Degisim deger={s.degisim} />
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {s.son ? tarihBicimle(s.son.olcum_at, dil, true) : t('seoIzleme.yonetici.hicOlcum')}
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={s.tarama_gun}
                        disabled={kaydedilen === s.site_id}
                        onChange={(e) => void siklik(s, Number(e.target.value))}
                        className="h-8 rounded-md border border-white/10 bg-background px-2 text-xs"
                        aria-label={t('seoIzleme.yonetici.siklik')}
                        data-testid={`seo-siklik-${s.site_id}`}
                      >
                        {[...new Set([...SIKLIKLAR, s.tarama_gun])].sort((a, b) => a - b).map((g) => (
                          <option key={g} value={g}>
                            {g === 0 ? t('seoIzleme.yonetici.kapali') : t('seoIzleme.yonetici.gunde', { sayi: g })}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2 text-end">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setAcik((o) => (o === s.site_id ? null : s.site_id))}
                        aria-expanded={acik === s.site_id}
                        data-testid={`seo-ozet-gecmis-${s.site_id}`}
                      >
                        {acik === s.site_id ? <ChevronUp className="me-1 h-4 w-4" /> : <ChevronDown className="me-1 h-4 w-4" />}
                        {acik === s.site_id ? t('seoIzleme.yonetici.kapat') : t('seoIzleme.yonetici.gecmis')}
                      </Button>
                    </td>
                  </tr>
                  {acik === s.site_id && (
                    <tr className="border-t border-white/10 bg-white/[0.02]">
                      <td colSpan={8} className="px-3 py-4">
                        {/* Telefonda tablo yatay kayıyor; geçmiş kartı görünür genişlikte kalsın. */}
                        <div className="sticky start-0 max-w-[min(48rem,calc(100vw-4rem))]">
                          <SeoKarti siteId={s.site_id} yonetici />
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
