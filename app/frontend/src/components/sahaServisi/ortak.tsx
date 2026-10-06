import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, X } from 'lucide-react';

import { BIRIMLER, type Durum, type Oncelik } from '@/lib/sahaServisi';

/** Faz 6S — saha servisi panelinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const GIRDI =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[84px] w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const DIS_DUGME = 'gap-1.5 !bg-transparent border-white/20';
export const BIRIM_SECENEKLERI = BIRIMLER;

export const DURUM_RENK: Record<Durum, string> = {
  yeni: 'border-sky-400/40 bg-sky-500/15 text-sky-200',
  planlandi: 'border-violet-400/40 bg-violet-500/15 text-violet-200',
  yolda: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  iste: 'border-orange-400/40 bg-orange-500/15 text-orange-200',
  tamamlandi: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  iptal: 'border-zinc-400/30 bg-zinc-500/10 text-zinc-300',
  ertelendi: 'border-rose-400/40 bg-rose-500/15 text-rose-200',
};

export const ONCELIK_RENK: Record<Oncelik, string> = {
  dusuk: 'border-white/10 bg-white/[0.04] text-muted-foreground',
  normal: 'border-white/15 bg-white/[0.06] text-white/80',
  yuksek: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  acil: 'border-red-400/50 bg-red-500/20 text-red-200',
};

export function Alan({ etiket, ipucu, children, className }: { etiket: string; ipucu?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block text-sm ${className ?? ''}`}>
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      {children}
      {ipucu && <span className="mt-1 block text-xs text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

export function Anahtar({ acik, onDegis, etiket, testid, devreDisi }: { acik: boolean; onDegis: (v: boolean) => void; etiket: string; testid?: string; devreDisi?: boolean }) {
  return (
    <label className={`flex cursor-pointer items-start gap-2 text-sm ${devreDisi ? 'opacity-50' : ''}`}>
      <input type="checkbox" className="mt-0.5 h-4 w-4 flex-none accent-purple-500" checked={acik} disabled={devreDisi} onChange={(e) => onDegis(e.target.checked)} data-testid={testid} />
      <span>{etiket}</span>
    </label>
  );
}

export function Rozet({ children, renk = 'border-white/10 bg-white/[0.05] text-muted-foreground', testid }: { children: ReactNode; renk?: string; testid?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${renk}`} data-testid={testid}>
      {children}
    </span>
  );
}

export function DurumRozeti({ durum }: { durum: Durum }) {
  const { t } = useTranslation();
  return (
    <Rozet renk={DURUM_RENK[durum]} testid="saha-durum">
      {t(`sahaServisi.durum.${durum}`)}
    </Rozet>
  );
}

export function OncelikRozeti({ oncelik }: { oncelik: Oncelik }) {
  const { t } = useTranslation();
  if (oncelik === 'normal') return null;
  return <Rozet renk={ONCELIK_RENK[oncelik]}>{t(`sahaServisi.oncelik.${oncelik}`)}</Rozet>;
}

export const Yukleniyor = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
  </div>
);

export function Bos({ children, testid }: { children: ReactNode; testid?: string }) {
  return (
    <p className="py-10 text-center text-sm text-muted-foreground" data-testid={testid}>
      {children}
    </p>
  );
}

export function Baslik({ children, ek }: { children: ReactNode; ek?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-base font-semibold">{children}</h3>
      {ek}
    </div>
  );
}

/** Panoya kopyala. */
export async function kopyala(metin: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(metin);
      return true;
    }
  } catch {
    /* yoksay */
  }
  return false;
}

/**
 * Basit yan panel (dialog): Escape ile kapanır, açılınca ilk alana odaklanır. Mobilde tam ekran.
 */
export function Panel({ baslik, onKapat, children, testid }: { baslik: string; onKapat: () => void; children: ReactNode; testid?: string }) {
  const { t } = useTranslation();
  const kutu = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onceki = document.activeElement as HTMLElement | null;
    const ilk = kutu.current?.querySelector<HTMLElement>('input, select, textarea, button:not([data-kapat])');
    ilk?.focus();
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onKapat();
    };
    document.addEventListener('keydown', tus);
    const tasma = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', tus);
      document.body.style.overflow = tasma;
      onceki?.focus?.();
    };
    // Yalnız açılışta.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm" onMouseDown={(e) => e.target === e.currentTarget && onKapat()}>
      <div
        ref={kutu}
        role="dialog"
        aria-modal="true"
        aria-label={baslik}
        className="flex h-full w-full max-w-2xl flex-col overflow-hidden border-white/10 bg-[#0b0614] shadow-2xl sm:border-s"
        data-testid={testid}
      >
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
          <h2 className="truncate text-lg font-semibold">{baslik}</h2>
          <button type="button" data-kapat onClick={onKapat} className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/[0.06] hover:text-white" aria-label={t('sahaServisi.kapat')}>
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  );
}
