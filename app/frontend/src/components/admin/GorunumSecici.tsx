import type { CSSProperties, ReactNode } from 'react';
import { Check, ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { GORUNUMLER, type Gorunum } from '@/lib/gorunum';

/**
 * Site Ayarları › Görünüm (Faz 8N): Klasik / Modern / Nebula (UI/UX).
 *
 * Her seçeneğin küçük önizlemesi yalnız CSS (satır içi stil; görsel dosya ve
 * yeni Tailwind sınıfı yok — ana stil dosyası büyümesin). Seçim taslağa yazılır,
 * gruptaki "Kaydet" düğmesi `site_gorunum` ayarını kaydeder; kaydedilen değer
 * bütün ziyaretçilerin varsayılanı olur (prerender bir sonraki derlemede onu
 * HTML'e basar, o zamana kadar Layout ayar gelince uygular).
 *
 * "Bu tarayıcıda dene" bağlantısı `?gorunum=<x>` ile yalnız yöneticinin
 * tarayıcısında açar (src/lib/gorunum.ts); `?gorunum=site` seçimi sıfırlar.
 * Metinler `ek/gorunumSecimi` paketinde (AdminPanel ekliLazy ile yüklüyor).
 */

const KESIK = (k: number) =>
  `polygon(${k}px 0, 100% 0, 100% calc(100% - ${k}px), calc(100% - ${k}px) 100%, 0 100%, 0 ${k}px)`;

function Kutu({ style, children }: { style: CSSProperties; children?: ReactNode }) {
  return <div style={{ position: 'absolute', ...style }}>{children}</div>;
}

/** Klasik: mor-siyah zemin, yumuşak cam kartlar, mor-pembe vurgu. */
function KlasikOnizleme() {
  const kart: CSSProperties = {
    top: 30,
    height: 36,
    borderRadius: 8,
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.12)',
  };
  return (
    <>
      <Kutu style={{ inset: 0, background: 'radial-gradient(circle at 18% 10%, rgba(168,85,247,0.3), transparent 55%), #07030d' }} />
      <Kutu style={{ left: 10, top: 12, width: '46%', height: 6, borderRadius: 3, background: 'linear-gradient(90deg,#c084fc,#f472b6)' }} />
      <Kutu style={{ ...kart, left: 10, width: 'calc(50% - 15px)' }} />
      <Kutu style={{ ...kart, right: 10, width: 'calc(50% - 15px)' }} />
    </>
  );
}

/** Modern: sade zemin, neon kenarlı kartlar, numara rozeti. */
function ModernOnizleme() {
  const kart = (renk: string): CSSProperties => ({
    top: 26,
    height: 40,
    borderRadius: 8,
    background: `linear-gradient(160deg, rgba(${renk},0.14), rgba(8,4,15,0.95) 50%)`,
    border: `1px solid rgba(${renk},0.7)`,
    boxShadow: `0 0 10px -3px rgba(${renk},0.8)`,
  });
  return (
    <>
      <Kutu style={{ inset: 0, background: '#08040f' }} />
      <Kutu style={{ ...kart('16,227,154'), left: 10, width: 'calc(50% - 15px)' }}>
        <Kutu style={{ left: 6, top: 6, padding: '2px 4px', borderRadius: 4, background: '#10e39a', color: '#05010a', fontSize: 8, fontWeight: 800, lineHeight: 1 }}>01</Kutu>
      </Kutu>
      <Kutu style={{ ...kart('168,85,247'), right: 10, width: 'calc(50% - 15px)' }}>
        <Kutu style={{ left: 6, top: 6, padding: '2px 4px', borderRadius: 4, background: '#a855f7', color: '#05010a', fontSize: 8, fontWeight: 800, lineHeight: 1 }}>02</Kutu>
      </Kutu>
      <Kutu style={{ left: 10, top: 11, width: '38%', height: 5, borderRadius: 3, background: '#10e39a', boxShadow: '0 0 8px rgba(16,227,154,0.8)' }} />
    </>
  );
}

/** Nebula: uzay zemini (bulutsu + yıldız), kesik köşeli holografik paneller, altıgen rozet. */
function NebulaOnizleme() {
  const panel = (renk: string, renk2: string): CSSProperties => ({
    top: 26,
    height: 40,
    clipPath: KESIK(7),
    background: `linear-gradient(135deg, rgb(${renk}), rgb(${renk2}))`,
  });
  const ic: CSSProperties = {
    inset: 1,
    clipPath: KESIK(6.5),
    background: 'linear-gradient(135deg, rgba(20,8,40,0.92), rgba(3,2,10,0.96))',
  };
  const rozet = (renk: string): CSSProperties => ({
    left: 7,
    top: 7,
    width: 15,
    height: 12,
    clipPath: 'polygon(25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%, 0 50%)',
    background: `rgb(${renk})`,
  });
  return (
    <>
      <Kutu
        style={{
          inset: 0,
          background: [
            'radial-gradient(1px 1px at 22% 18%, #fff, transparent)',
            'radial-gradient(1px 1px at 64% 12%, rgba(255,255,255,0.8), transparent)',
            'radial-gradient(1px 1px at 88% 34%, #fff, transparent)',
            'radial-gradient(1px 1px at 41% 88%, rgba(255,255,255,0.7), transparent)',
            'radial-gradient(circle at 12% 20%, rgba(168,85,247,0.55), transparent 48%)',
            'radial-gradient(circle at 92% 90%, rgba(46,245,150,0.35), transparent 50%)',
            '#03020a',
          ].join(','),
        }}
      />
      <Kutu style={{ left: 10, top: 11, width: '40%', height: 5, background: 'linear-gradient(90deg,#c084fc,#2ef596)', boxShadow: '0 0 8px rgba(168,85,247,0.8)' }} />
      <Kutu style={{ ...panel('192,132,252', '120,60,220'), left: 10, width: 'calc(50% - 15px)' }}>
        <Kutu style={ic} />
        <Kutu style={rozet('192,132,252')} />
      </Kutu>
      <Kutu style={{ ...panel('46,245,150', '20,170,110'), right: 10, width: 'calc(50% - 15px)' }}>
        <Kutu style={ic} />
        <Kutu style={rozet('46,245,150')} />
      </Kutu>
    </>
  );
}

const ONIZLEMELER: Record<Gorunum, () => JSX.Element> = {
  klasik: KlasikOnizleme,
  modern: ModernOnizleme,
  nebula: NebulaOnizleme,
};

export default function GorunumSecici({
  etiket,
  deger,
  kayitli,
  degistir,
}: {
  etiket: string;
  deger: string;
  kayitli: string;
  degistir: (v: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3" data-testid="gorunum-secici">
      <div className="grid gap-3 sm:grid-cols-3" role="group" aria-label={etiket}>
        {GORUNUMLER.map((g) => {
          const Onizleme = ONIZLEMELER[g];
          const secili = deger === g;
          return (
            <button
              key={g}
              type="button"
              aria-pressed={secili}
              data-testid={`gorunum-secenek-${g}`}
              onClick={() => degistir(g)}
              className={`flex flex-col gap-2 rounded-xl border p-2.5 text-start transition-colors ${
                secili ? 'border-emerald-400/70 bg-emerald-500/10' : 'border-white/10 hover:bg-white/5'
              }`}
            >
              <div aria-hidden="true" style={{ position: 'relative', height: 76, borderRadius: 8, overflow: 'hidden' }}>
                <Onizleme />
              </div>
              <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                {secili && <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" aria-hidden="true" />}
                {t(`gorunumSecimi.${g}Ad`)}
              </span>
              <span className="text-xs leading-relaxed text-muted-foreground">{t(`gorunumSecimi.${g}Aciklama`)}</span>
              {kayitli === g && (
                <span className="self-start rounded-full border border-emerald-400/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
                  {t('gorunumSecimi.sitede')}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">{t('gorunumSecimi.kaydetIpucu')}</p>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{t('gorunumSecimi.dene')}:</span>
        {GORUNUMLER.map((g) => (
          <a
            key={g}
            href={`/?gorunum=${g}`}
            target="_blank"
            rel="noopener"
            data-testid={`gorunum-dene-${g}`}
            className="inline-flex items-center gap-1 text-emerald-300 underline-offset-2 hover:underline"
          >
            {t(`gorunumSecimi.${g}Ad`)}
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        ))}
        <a href="/?gorunum=site" target="_blank" rel="noopener" className="text-muted-foreground underline underline-offset-2 hover:text-foreground">
          {t('gorunumSecimi.sifirla')}
        </a>
      </p>
    </div>
  );
}
