import { Suspense, useCallback, useEffect, useState } from 'react';
import { Check, Copy, ExternalLink, Loader2, Wrench } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import BitisRozetleri from '@/components/BitisRozetleri';
import UptimeGrafigi from '@/components/UptimeGrafigi';
import UptimeOzetSatiri from '@/components/UptimeOzetSatiri';
import { Button } from '@/components/ui/button';
import { ekliLazy } from '@/i18n/ekliLazy';
import {
  BakimHatasi,
  kendiBakimKartlarim,
  musteriDurumSayfasi,
  tarihBicimle,
  type BakimKarti,
} from '@/lib/siteBakim';

// Faz 2H: "SEO ve hız" bölümü — kendi kodu ve iki ek paketi (bulgu metinleri
// `siteAnalizi`, bölüm metinleri `seoIzleme`) yalnız bu kart açılınca iner.
const SeoKarti = ekliLazy(['siteAnalizi', 'seoIzleme'], () => import('@/components/SeoKarti'));

/**
 * Müşteri › "Sitem" sekmesi › bakım ve erişilebilirlik kartı (Faz 2A).
 *
 * Salt okunur: alan adı / SSL / hosting bitişleri, uptime özeti ve 90
 * günlük grafik, son kesintiler. Müşterinin değiştirebildiği tek şey
 * herkese açık durum sayfası (aç/kapa, arama motorlarına açık mı).
 * Uptime modülü kapalıysa grafik yerine kısa bir not. Faz 2H: adresi olan
 * sitede "SEO ve hız" bölümü (tembel `SeoKarti`).
 */
export default function SitemBakim() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [kartlar, setKartlar] = useState<BakimKarti[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [mesgul, setMesgul] = useState<number | null>(null);
  const [kopyalanan, setKopyalanan] = useState<number | null>(null);

  const yukle = useCallback(async () => {
    try {
      setKartlar(await kendiBakimKartlarim());
    } catch {
      setKartlar([]);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const durumSayfasi = async (k: BakimKarti, acik: boolean, index?: boolean) => {
    setMesgul(k.site_id);
    try {
      const d = await musteriDurumSayfasi(k.site_id, acik, index);
      setKartlar((o) =>
        o.map((x) =>
          x.site_id === k.site_id
            ? {
                ...x,
                durum_adresi: d.durum_adresi,
                izleme: { ...x.izleme, durum_sayfasi_acik: d.durum_sayfasi_acik, durum_index: d.durum_index, durum_slug: d.durum_slug },
              }
            : x,
        ),
      );
      if (index === undefined) toast.success(t(acik ? 'siteBakim.durumSayfasi.acildi' : 'siteBakim.durumSayfasi.kapandi'));
    } catch (h) {
      const kod = h instanceof BakimHatasi ? h.kod : 'genel';
      toast.error(t(`siteBakim.hata.${kod}`, { defaultValue: t('siteBakim.hata.genel') }));
    } finally {
      setMesgul(null);
    }
  };

  const kopyala = async (k: BakimKarti) => {
    if (!k.durum_adresi) return;
    try {
      await navigator.clipboard.writeText(`${window.location.origin}${k.durum_adresi}`);
      setKopyalanan(k.site_id);
      setTimeout(() => setKopyalanan(null), 2000);
    } catch {
      /* bağlantı zaten görünür */
    }
  };

  if (yukleniyor) {
    return <Loader2 className="mt-6 h-4 w-4 animate-spin text-muted-foreground" />;
  }
  if (kartlar.length === 0) return null;

  return (
    <div className="mt-8 space-y-4">
      <div>
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <Wrench className="h-5 w-5" />
          {t('siteBakim.musteri.baslik')}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('siteBakim.musteri.aciklama')}</p>
      </div>
      {kartlar.map((k) => (
        <div
          key={k.site_id}
          className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-5"
          data-testid={`sitem-bakim-${k.site_id}`}
        >
          <div className="mb-3 min-w-0">
            <p className="truncate font-medium">{k.ad}</p>
            {k.adres && <p className="truncate text-xs text-muted-foreground">{k.adres}</p>}
          </div>
          <BitisRozetleri izleme={k.izleme} siteId={k.site_id} />
          <p className="mt-2 text-[11px] text-muted-foreground">
            {[
              k.izleme.alan_saglayici && `${t('siteBakim.bilgi.alanSaglayici')}: ${k.izleme.alan_saglayici}`,
              k.izleme.hosting_saglayici && `${t('siteBakim.bilgi.hostingSaglayici')}: ${k.izleme.hosting_saglayici}`,
              k.izleme.alan_bitis && `${t('siteBakim.bilgi.alanBitis')}: ${tarihBicimle(k.izleme.alan_bitis, dil)}`,
              k.izleme.hosting_bitis && `${t('siteBakim.bilgi.hostingBitis')}: ${tarihBicimle(k.izleme.hosting_bitis, dil)}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>

          <div className="mt-4 border-t border-white/10 pt-4">
            {!k.uptime_modulu ? (
              <p className="text-xs text-muted-foreground">{t('siteBakim.musteri.uptimeKapali')}</p>
            ) : !k.uptime || !k.uptime.kontrol_sayisi ? (
              <p className="text-xs text-muted-foreground">{t('siteBakim.musteri.kontrolYok')}</p>
            ) : (
              <div className="space-y-3">
                <UptimeOzetSatiri ozet={k.uptime} siteId={k.site_id} />
                <UptimeGrafigi gunler={k.uptime.gunler} ortalama={k.uptime.oran_90g} testId={`sitem-grafik-${k.site_id}`} />
              </div>
            )}
          </div>

          {k.adres && (
            <div className="mt-4 border-t border-white/10 pt-4">
              <Suspense fallback={<Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}>
                <SeoKarti siteId={k.site_id} />
              </Suspense>
            </div>
          )}

          {k.uptime_modulu && (
            <div className="mt-4 border-t border-white/10 pt-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium">{t('siteBakim.durumSayfasi.baslik')}</p>
                  <p className="text-[11px] text-muted-foreground">{t('siteBakim.durumSayfasi.musteriNotu')}</p>
                </div>
                <Button
                  size="sm"
                  variant={k.izleme.durum_sayfasi_acik ? 'secondary' : 'default'}
                  disabled={mesgul === k.site_id}
                  onClick={() => void durumSayfasi(k, !k.izleme.durum_sayfasi_acik)}
                  data-testid={`sitem-durum-ac-${k.site_id}`}
                >
                  {mesgul === k.site_id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {k.izleme.durum_sayfasi_acik ? t('siteBakim.durumSayfasi.kapat') : t('siteBakim.durumSayfasi.ac')}
                </Button>
              </div>
              {k.durum_adresi && (
                <div className="mt-2 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href={k.durum_adresi}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex min-w-0 items-center gap-1 break-all text-sm text-cyan-300 hover:underline"
                    >
                      {`${window.location.origin}${k.durum_adresi}`}
                      <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                    </a>
                    <Button size="sm" variant="ghost" onClick={() => void kopyala(k)}>
                      {kopyalanan === k.site_id ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
                      {kopyalanan === k.site_id ? t('siteBakim.durumSayfasi.kopyalandi') : t('siteBakim.durumSayfasi.kopyala')}
                    </Button>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={k.izleme.durum_index}
                      disabled={mesgul === k.site_id}
                      onChange={(e) => void durumSayfasi(k, true, e.target.checked)}
                    />
                    {t('siteBakim.durumSayfasi.index')}
                  </label>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
