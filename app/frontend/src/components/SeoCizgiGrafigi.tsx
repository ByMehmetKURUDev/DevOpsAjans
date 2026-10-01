import { useTranslation } from 'react-i18next';

import { tarihBicimle, type SeoOlcumKisa } from '@/lib/seoIzleme';

/**
 * Son N günün SEO/hız puanı — kütüphanesiz küçük SVG çizgi grafiği.
 *
 * Yatay eksen zaman (N gün önce → bugün; ölçümler gerçek tarihine göre
 * yerleşiyor, haftalık ölçümde aralar eşit), dikey eksen 0–100. Kesikli
 * yatay çizgiler Lighthouse eşikleri (50 ve 90). Düz çizgi genel puan,
 * kesikli mor çizgi mobil hız puanı. `viewBox` oranı sabit: telefonda da
 * taşmadan küçülüyor. Zaman ekseni Arapçada da soldan sağa (`dir="ltr"`).
 */
const G = 320;
const Y = 110;
const SOL = 22;
const SAG = 6;
const UST = 6;
const ALT = 14;

function konum(an: number, bas: number, bit: number): number {
  const oran = bit > bas ? (an - bas) / (bit - bas) : 1;
  return SOL + Math.max(0, Math.min(1, oran)) * (G - SOL - SAG);
}

/**
 * Zamana göre yerleşim, ama aynı gün yapılan ölçümler (elle tarama) üst üste
 * binmesin: ardışık noktalar arasında en az `AYRIM` birim. Sağa taşan son
 * nokta kenara çekilip öncekiler geriye doğru itiliyor (sıra korunuyor).
 */
function yerlestir(xs: number[]): number[] {
  const sol = SOL;
  const sag = G - SAG;
  const ayrim = xs.length > 1 ? Math.min(8, (sag - sol) / (xs.length - 1)) : 0;
  const x = [...xs];
  for (let i = 1; i < x.length; i++) x[i] = Math.max(x[i], x[i - 1] + ayrim);
  if (x.length && x[x.length - 1] > sag) {
    x[x.length - 1] = sag;
    for (let i = x.length - 2; i >= 0; i--) x[i] = Math.min(x[i], x[i + 1] - ayrim);
  }
  return x.map((d) => Math.max(sol, d));
}

function yukseklik(puan: number): number {
  return UST + (1 - Math.max(0, Math.min(100, puan)) / 100) * (Y - UST - ALT);
}

export default function SeoCizgiGrafigi({
  olcumler,
  gun,
  testId,
}: {
  olcumler: SeoOlcumKisa[];
  gun: number;
  testId?: string;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const bit = Date.now();
  const bas = bit - gun * 86400000;
  const noktalar = olcumler
    .filter((o) => o.durum === 'tamam' && o.olcum_at)
    .map((o) => ({ ...o, an: new Date(o.olcum_at as string).getTime() }))
    .filter((o) => !Number.isNaN(o.an))
    .sort((a, b) => a.an - b.an);
  const xler = yerlestir(noktalar.map((o) => konum(o.an, bas, bit)));
  const x = new Map(noktalar.map((o, i) => [o.id, xler[i]]));
  const genel = noktalar.filter((o) => o.genel_puan !== null);
  const mobil = noktalar.filter((o) => o.mobil_puan !== null);
  const cizgi = (liste: typeof noktalar, alan: 'genel_puan' | 'mobil_puan') =>
    liste.map((o) => `${(x.get(o.id) as number).toFixed(1)},${yukseklik(o[alan] as number).toFixed(1)}`).join(' ');
  const son = genel.length ? genel[genel.length - 1].genel_puan : null;

  return (
    // Geniş ekranda çizgi orantısız büyümesin (yükseklik genişlikle ölçekleniyor).
    <div className="max-w-2xl" data-testid={testId}>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{t('seoIzleme.grafik.baslik', { sayi: gun })}</p>
      <svg
        viewBox={`0 0 ${G} ${Y}`}
        className="h-auto w-full"
        role="img"
        aria-label={t('seoIzleme.grafik.aria', { sayi: gun, olcum: genel.length, puan: son ?? '—' })}
        style={{ direction: 'ltr' }}
      >
        {[0, 50, 90, 100].map((p) => (
          <g key={p}>
            <line
              x1={SOL}
              x2={G - SAG}
              y1={yukseklik(p)}
              y2={yukseklik(p)}
              stroke="currentColor"
              strokeOpacity={p === 50 || p === 90 ? 0.25 : 0.1}
              strokeDasharray={p === 50 || p === 90 ? '3 3' : undefined}
              strokeWidth="0.6"
            />
            <text x={SOL - 4} y={yukseklik(p) + 2.5} textAnchor="end" fontSize="7" fill="currentColor" fillOpacity="0.55">
              {p}
            </text>
          </g>
        ))}
        {mobil.length > 1 && (
          <polyline
            points={cizgi(mobil, 'mobil_puan')}
            fill="none"
            stroke="#c084fc"
            strokeWidth="1.2"
            strokeDasharray="4 3"
            strokeLinejoin="round"
            data-testid="seo-cizgi-mobil"
          />
        )}
        {genel.length > 1 && (
          <polyline
            points={cizgi(genel, 'genel_puan')}
            fill="none"
            stroke="#22d3ee"
            strokeWidth="1.8"
            strokeLinejoin="round"
            strokeLinecap="round"
            data-testid="seo-cizgi"
          />
        )}
        {genel.map((o) => (
          <circle key={o.id} cx={x.get(o.id)} cy={yukseklik(o.genel_puan as number)} r="2.4" fill="#22d3ee">
            <title>{`${tarihBicimle(o.olcum_at, dil, true)} · ${o.genel_puan}`}</title>
          </circle>
        ))}
        <text x={SOL} y={Y - 2} fontSize="7" fill="currentColor" fillOpacity="0.55">
          {tarihBicimle(new Date(bas).toISOString(), dil)}
        </text>
        <text x={G - SAG} y={Y - 2} fontSize="7" textAnchor="end" fill="currentColor" fillOpacity="0.55">
          {tarihBicimle(new Date(bit).toISOString(), dil)}
        </text>
      </svg>
      <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-cyan-400" aria-hidden="true" />
          {t('seoIzleme.genel')}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0 w-4 border-t border-dashed border-purple-400" aria-hidden="true" />
          {t('seoIzleme.mobil')}
        </span>
        {genel.length < 2 && <span>{t('seoIzleme.grafik.tekOlcum')}</span>}
      </div>
    </div>
  );
}
