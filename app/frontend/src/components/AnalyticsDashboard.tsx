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
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { createClient } from '@metagptx/web-sdk';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

const client = createClient();

interface Snapshot {
  id: number | string;
  channel: string;
  metric_key: string;
  metric_label?: string;
  metric_value: number;
  change_pct?: number;
  unit?: string;
  snapshot_date?: string;
}

/** Kanal tanımları — başlıklar i18n anahtarı üzerinden çözülür. */
const CHANNELS: {
  key: string;
  titleKey: string;
  icon: typeof Activity;
  gradient: string;
}[] = [
  {
    key: 'traffic',
    titleKey: 'admin.trafficTitle',
    icon: Activity,
    gradient: 'from-purple-600 to-pink-600',
  },
  {
    key: 'seo',
    titleKey: 'admin.seoTitle',
    icon: Search,
    gradient: 'from-cyan-500 to-purple-600',
  },
  {
    key: 'ads',
    titleKey: 'admin.adsTitle',
    icon: Megaphone,
    gradient: 'from-orange-500 to-pink-600',
  },
  {
    key: 'social',
    titleKey: 'admin.socialTitle',
    icon: Share2,
    gradient: 'from-emerald-500 to-cyan-500',
  },
];

/** Sayısal metrik değerini aktif dilin biçimine göre formatlar. */
function formatValue(v: number, locale: string, unit?: string) {
  const formatted =
    Math.abs(v) >= 1000
      ? v.toLocaleString(locale, { maximumFractionDigits: 0 })
      : v.toLocaleString(locale, { maximumFractionDigits: 1 });
  if (unit === '$') return `$${formatted}`;
  if (unit === '%') return `${formatted}%`;
  return formatted;
}

interface AnalyticsDashboardProps {
  ga4Id?: string;
}

export default function AnalyticsDashboard({
  ga4Id,
}: AnalyticsDashboardProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language || 'tr';
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await client.entities.analytics_snapshots.query({
        sort: '-snapshot_date',
        limit: 200,
      });
      setSnapshots((res?.data?.items ?? []) as Snapshot[]);
      setLastUpdated(new Date());
    } catch (e) {
      const err = e as { message?: string };
      setError(err?.message || t('admin.analyticsLoadError'));
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

  const byChannel = useMemo(() => {
    const map: Record<string, Snapshot[]> = {};
    snapshots.forEach((s) => {
      if (!map[s.channel]) map[s.channel] = [];
      // Aynı metrik için sadece en güncel kaydı tut
      if (!map[s.channel].some((m) => m.metric_key === s.metric_key)) {
        map[s.channel].push(s);
      }
    });
    return map;
  }, [snapshots]);

  const chartData = useMemo(() => {
    return CHANNELS.map((c) => {
      const items = byChannel[c.key] ?? [];
      const primary =
        items.find((i) =>
          ['sessions', 'organic_clicks', 'clicks', 'reach'].includes(
            i.metric_key
          )
        ) ?? items[0];
      return {
        name: t(c.titleKey),
        deger: primary ? primary.metric_value : 0,
      };
    });
  }, [byChannel, t]);

  if (loading && snapshots.length === 0) {
    return (
      <div className="py-16 flex items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />{' '}
        {t('admin.analyticsLoading')}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{t('admin.liveView')}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {lastUpdated
              ? `${t('admin.lastUpdate')}: ${lastUpdated.toLocaleTimeString(
                  locale
                )} • ${t('admin.autoRefresh')}`
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
          <Button
            onClick={load}
            variant="outline"
            size="sm"
            className="gap-2 !bg-transparent border-white/20"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            {t('admin.refresh')}
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          {error}
        </div>
      )}

      {CHANNELS.map((channel) => {
        const items = byChannel[channel.key] ?? [];
        return (
          <div key={channel.key}>
            <div className="flex items-center gap-3 mb-4">
              <div
                className={`w-9 h-9 rounded-lg bg-gradient-to-br ${channel.gradient} flex items-center justify-center`}
              >
                <channel.icon className="h-4 w-4 text-white" />
              </div>
              <h3 className="text-lg font-semibold">{t(channel.titleKey)}</h3>
            </div>
            {items.length === 0 ? (
              <div className="p-6 rounded-xl glass text-sm text-muted-foreground">
                {t('admin.noChannelData')}
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {items.map((m) => {
                  const up = (m.change_pct ?? 0) >= 0;
                  return (
                    <div key={m.id} className="p-5 rounded-2xl glass">
                      <p className="text-xs uppercase tracking-widest text-muted-foreground mb-2">
                        {m.metric_label || m.metric_key}
                      </p>
                      <p className="text-2xl font-bold">
                        {formatValue(m.metric_value, locale, m.unit)}
                      </p>
                      {typeof m.change_pct === 'number' && (
                        <div
                          className={`mt-2 inline-flex items-center gap-1 text-xs font-medium ${
                            up ? 'text-emerald-400' : 'text-pink-400'
                          }`}
                        >
                          {up ? (
                            <TrendingUp className="h-3.5 w-3.5" />
                          ) : (
                            <TrendingDown className="h-3.5 w-3.5" />
                          )}
                          {up ? '+' : ''}
                          {m.change_pct}%
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}

      <div className="p-6 rounded-2xl glass">
        <h3 className="text-lg font-semibold mb-6">
          {t('admin.channelComparison')}
        </h3>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(255,255,255,0.08)"
              />
              <XAxis
                dataKey="name"
                stroke="#b9a9d6"
                fontSize={12}
                tickLine={false}
              />
              <YAxis stroke="#b9a9d6" fontSize={12} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: '#150a2b',
                  border: '1px solid rgba(139,61,255,0.4)',
                  borderRadius: 12,
                  color: '#ece6ff',
                }}
              />
              <Bar dataKey="deger" fill="#8b3dff" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}