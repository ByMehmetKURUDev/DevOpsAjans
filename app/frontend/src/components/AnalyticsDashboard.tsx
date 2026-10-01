import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Loader2,
  TrendingUp,
  TrendingDown,
  Search,
  Megaphone,
  Share2,
  Activity,
  RefreshCw,
  ExternalLink,
  Youtube,
  Info,
  Link2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { hataMetni, panoGetir, type ListeSatiri, type PanoKanali, type PanoSatiri, type PanoVerisi } from '@/lib/baglantilar';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

/**
 * Yönetici › Anlık Analitik.
 *
 * Faz 3B: veri `/api/v1/baglantilar/pano`'dan geliyor. Kanal başına kural
 * sunucuda: gerçek veri (Google ya da elle girilmiş) varsa o kanalın örnek
 * satırları hiç gelmiyor; yalnız örnek varsa satırlar `ornek` işaretli gelir
 * ve kartların üstünde "Örnek veri" şeridi + Bağlantılar düğmesi çıkar.
 * Metin ek paketten (`baglantilar`) — bu bileşen `ekliLazy` ile yükleniyor.
 */

/** Kanal tanımları — başlıklar i18n anahtarı üzerinden çözülür. */
const CHANNELS: Record<string, { titleKey: string; icon: typeof Activity; gradient: string }> = {
  traffic: { titleKey: 'admin.trafficTitle', icon: Activity, gradient: 'from-purple-600 to-pink-600' },
  seo: { titleKey: 'admin.seoTitle', icon: Search, gradient: 'from-cyan-500 to-purple-600' },
  youtube: { titleKey: 'baglantilar.pano.youtubeBaslik', icon: Youtube, gradient: 'from-pink-600 to-orange-500' },
  ads: { titleKey: 'admin.adsTitle', icon: Megaphone, gradient: 'from-orange-500 to-pink-600' },
  social: { titleKey: 'admin.socialTitle', icon: Share2, gradient: 'from-emerald-500 to-cyan-500' },
};

/** Artışı kötü olan metrikler (renk ters). */
const DUSUK_IYI = new Set(['bounce_rate', 'avg_position']);
/** Grafikte kanalı temsil eden metrik (ilk bulunan). */
const BIRINCIL = ['sessions', 'organic_clicks', 'views', 'clicks', 'reach'];

interface AnalyticsDashboardProps {
  ga4Id?: string;
  /** "Bağlantılar" sekmesine geçiş (pano şeridindeki düğme). */
  onBaglantilaraGit?: () => void;
}

export default function AnalyticsDashboard({ ga4Id, onBaglantilaraGit }: AnalyticsDashboardProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language || 'tr';
  const [pano, setPano] = useState<PanoVerisi | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setPano(await panoGetir());
      setLastUpdated(new Date());
    } catch (e) {
      setError(hataMetni(t, e) || t('admin.analyticsLoadError'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // 60 saniyede bir otomatik yenileme — anlık takip için
    const timer = window.setInterval(load, 60000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const kanalAdi = (ad: string) => (CHANNELS[ad] ? t(CHANNELS[ad].titleKey) : ad);

  /** Bilinen kanallar her zaman (boşsa "veri yok"), bilinmeyenler veriden. */
  const kanallar = useMemo<PanoKanali[]>(() => {
    const gelen = new Map((pano?.kanallar ?? []).map((k) => [k.kanal, k]));
    const sonuc: PanoKanali[] = Object.keys(CHANNELS).map(
      (ad) => gelen.get(ad) ?? { kanal: ad, ornek: false, kaynaklar: [], metrikler: [], tarih: null }
    );
    for (const k of pano?.kanallar ?? []) if (!CHANNELS[k.kanal]) sonuc.push(k);
    return sonuc;
  }, [pano]);

  const chartData = useMemo(
    () =>
      kanallar
        .filter((k) => k.metrikler.length > 0)
        .map((k) => {
          const birincil = k.metrikler.find((m) => BIRINCIL.includes(m.metric_key)) ?? k.metrikler[0];
          const ad = CHANNELS[k.kanal] ? t(CHANNELS[k.kanal].titleKey) : k.kanal;
          return {
            name: k.ornek ? `${ad} (${t('baglantilar.pano.ornekRozet')})` : ad,
            deger: birincil ? birincil.metric_value : 0,
          };
        }),
    [kanallar, t]
  );

  if (loading && !pano) {
    return (
      <div className="py-16 flex items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> {t('admin.analyticsLoading')}
      </div>
    );
  }

  const etiket = (m: PanoSatiri) =>
    t(`baglantilar.metrik.${m.metric_key}`, { defaultValue: m.metric_label || m.metric_key });

  const deger = (m: PanoSatiri) => {
    const v = m.metric_value;
    const formatted =
      Math.abs(v) >= 1000
        ? v.toLocaleString(locale, { maximumFractionDigits: 0 })
        : v.toLocaleString(locale, { maximumFractionDigits: m.unit === '%' ? 2 : 1 });
    if (m.unit === '$') return `$${formatted}`;
    if (m.unit === '%') return `${formatted}%`;
    if (m.unit === 'sn' || m.unit === 'dk') return `${formatted} ${t(`baglantilar.birim.${m.unit}`)}`;
    return formatted;
  };

  const baglanDugmesi = (kucuk: boolean) =>
    onBaglantilaraGit ? (
      <Button
        size="sm"
        variant={kucuk ? 'outline' : 'default'}
        className={kucuk ? '!bg-transparent border-white/20 h-7 px-2 text-xs' : ''}
        onClick={onBaglantilaraGit}
        data-testid={kucuk ? undefined : 'ornek-serit-baglan'}
      >
        <Link2 className={kucuk ? 'mr-1 h-3.5 w-3.5' : 'mr-2 h-4 w-4'} />
        {t('baglantilar.pano.baglan')}
      </Button>
    ) : null;

  const liste = (tur: 'sorgular' | 'sayfalar', baslik: string) => {
    const l = pano?.listeler?.[tur];
    if (!l || !l.satirlar.length) return null;
    return (
      <div className="p-5 rounded-2xl glass overflow-x-auto" data-testid={`liste-${tur}`}>
        <h4 className="text-sm font-semibold mb-3">{baslik}</h4>
        <table className="w-full text-xs">
          <thead className="text-muted-foreground">
            <tr className="text-start">
              <th className="py-1 pe-2 font-medium text-start">{t(`baglantilar.pano.sutun.${tur === 'sorgular' ? 'sorgu' : 'sayfa'}`)}</th>
              <th className="py-1 px-2 font-medium text-end">{t('baglantilar.pano.sutun.tiklama')}</th>
              <th className="py-1 px-2 font-medium text-end">{t('baglantilar.pano.sutun.gosterim')}</th>
              <th className="py-1 px-2 font-medium text-end">{t('baglantilar.pano.sutun.to')}</th>
              <th className="py-1 ps-3 font-medium text-end">{t('baglantilar.pano.sutun.sira')}</th>
            </tr>
          </thead>
          <tbody>
            {l.satirlar.map((r: ListeSatiri) => (
              <tr key={r.anahtar} className="border-t border-white/5">
                <td className="py-1.5 pe-2 max-w-[18rem] truncate" title={r.anahtar} dir="auto">
                  {r.anahtar}
                </td>
                <td className="py-1.5 px-2 text-end">{r.tiklama.toLocaleString(locale)}</td>
                <td className="py-1.5 px-2 text-end">{r.gosterim.toLocaleString(locale)}</td>
                <td className="py-1.5 px-2 text-end">{r.to.toLocaleString(locale, { maximumFractionDigits: 2 })}%</td>
                <td className="py-1.5 ps-3 text-end">{r.sira.toLocaleString(locale, { maximumFractionDigits: 1 })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="space-y-8" data-testid="analitik-pano">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{t('admin.liveView')}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {lastUpdated
              ? `${t('admin.lastUpdate')}: ${lastUpdated.toLocaleTimeString(locale)} • ${t('admin.autoRefresh')}`
              : t('admin.dataPreparing')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {ga4Id && (
            <a
              href={`https://analytics.google.com/analytics/web/#/p/${ga4Id}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-purple-400 hover:text-pink-400 transition-colors"
            >
              GA4: {ga4Id} <ExternalLink className="h-3 w-3" />
            </a>
          )}
          <Button onClick={load} variant="outline" size="sm" className="gap-2 !bg-transparent border-white/20">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            {t('admin.refresh')}
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-sm">{error}</div>
      )}

      {pano?.yalniz_ornek && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-400/40 bg-amber-500/10 p-4 text-sm text-amber-100"
          data-testid="ornek-serit"
          role="status"
        >
          <span className="flex items-start gap-2">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              <strong>{t('baglantilar.pano.ornekBaslik')}</strong> — {t('baglantilar.pano.ornekSerit')}
            </span>
          </span>
          {baglanDugmesi(false)}
        </div>
      )}

      {kanallar.map((k) => {
        const tanim = CHANNELS[k.kanal] ?? { titleKey: k.kanal, icon: Activity, gradient: 'from-purple-600 to-pink-600' };
        const Ikon = tanim.icon;
        const gercekKaynaklar = k.kaynaklar.filter((x) => x !== 'ornek');
        return (
          <div key={k.kanal} data-testid={`kanal-${k.kanal}`} data-ornek={k.ornek ? 'evet' : 'hayir'}>
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <div className={`w-9 h-9 rounded-lg bg-gradient-to-br ${tanim.gradient} flex items-center justify-center`}>
                <Ikon className="h-4 w-4 text-white" />
              </div>
              <h3 className="text-lg font-semibold">{kanalAdi(k.kanal)}</h3>
              {k.ornek && (
                <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider text-amber-200">
                  {t('baglantilar.pano.ornekRozet')}
                </span>
              )}
              {!k.ornek && gercekKaynaklar.length > 0 && (
                <span className="text-xs text-muted-foreground" data-testid={`kaynak-${k.kanal}`}>
                  {gercekKaynaklar.map((x) => t(`baglantilar.pano.kaynak.${x}`, { defaultValue: x })).join(' · ')}
                  {gercekKaynaklar.some((x) => x !== 'elle') && ` · ${t('baglantilar.pano.donem')}`}
                  {k.tarih && ` · ${t('baglantilar.pano.sonGuncelleme')}: ${k.tarih}`}
                </span>
              )}
            </div>
            {k.ornek && !pano?.yalniz_ornek && (
              <div
                className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100"
                data-testid={`ornek-serit-${k.kanal}`}
              >
                <span>{t('baglantilar.pano.ornekSeritKanal')}</span>
                {baglanDugmesi(true)}
              </div>
            )}
            {k.metrikler.length === 0 ? (
              <div className="p-6 rounded-xl glass text-sm text-muted-foreground">{t('admin.noChannelData')}</div>
            ) : (
              <div className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-4 ${k.ornek ? 'opacity-70' : ''}`}>
                {k.metrikler.map((m) => {
                  const artis = (m.change_pct ?? 0) >= 0;
                  const iyi = DUSUK_IYI.has(m.metric_key) ? !artis : artis;
                  return (
                    <div
                      key={m.id}
                      className="p-5 rounded-2xl glass"
                      data-testid={`metrik-${k.kanal}-${m.metric_key}`}
                      data-deger={m.metric_value}
                    >
                      <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">{etiket(m)}</p>
                      <p className="cam-parla text-2xl font-bold">{deger(m)}</p>
                      {typeof m.change_pct === 'number' && (
                        <div
                          className={`mt-2 inline-flex items-center gap-1 text-xs font-medium ${
                            iyi ? 'text-emerald-400' : 'text-pink-400'
                          }`}
                        >
                          {artis ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                          {artis ? '+' : ''}
                          {m.change_pct}%
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {k.kanal === 'seo' && !k.ornek && (
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {liste('sorgular', t('baglantilar.pano.enCokSorgu'))}
                {liste('sayfalar', t('baglantilar.pano.enCokSayfa'))}
              </div>
            )}
          </div>
        );
      })}

      <div className="p-6 rounded-2xl glass">
        <h3 className="text-lg font-semibold mb-6">{t('admin.channelComparison')}</h3>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
              <XAxis dataKey="name" stroke="#b9a9d6" fontSize={12} tickLine={false} />
              <YAxis stroke="#b9a9d6" fontSize={12} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: '#150a2b',
                  border: '1px solid rgb(var(--hero-a) / 0.4)',
                  borderRadius: 12,
                  color: '#ece6ff',
                }}
              />
              <Bar dataKey="deger" fill="rgb(var(--hero-a))" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
