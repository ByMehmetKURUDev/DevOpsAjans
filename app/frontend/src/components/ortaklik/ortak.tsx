import type { ReactNode } from 'react';

/** Faz 5K — ortaklık panellerinin (müşteri + yönetici) ortak küçük parçaları; mevcut sınıf dili (`cam-kart`). */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const GIRDI =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[96px] w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';

export const DURUM_RENGI: Record<string, string> = {
  beklemede: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  bekliyor: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  onaylandi: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  odeme_talebinde: 'border-sky-400/30 bg-sky-500/10 text-sky-200',
  odendi: 'border-purple-400/30 bg-purple-500/10 text-purple-200',
  iptal: 'border-white/15 bg-white/5 text-muted-foreground',
  reddedildi: 'border-red-400/30 bg-red-500/10 text-red-200',
  askida: 'border-red-400/30 bg-red-500/10 text-red-200',
};

export function Rozet({ durum, children }: { durum: string; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${DURUM_RENGI[durum] ?? DURUM_RENGI.iptal}`}
      data-durum={durum}
    >
      {children}
    </span>
  );
}

export function Alan({ etiket, ipucu, children, className }: { etiket: string; ipucu?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block text-sm ${className ?? ''}`}>
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      {children}
      {ipucu && <span className="mt-1 block text-xs text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

export function AltDugme({ secili, onClick, children, testid }: { secili: boolean; onClick: () => void; children: ReactNode; testid?: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={secili}
      onClick={onClick}
      className={`flex min-h-[40px] flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
        secili ? 'bg-purple-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
      }`}
      data-ortaklik-alt={testid}
    >
      {children}
    </button>
  );
}

export function SayiKarti({ etiket, deger, alt, testid }: { etiket: string; deger: ReactNode; alt?: ReactNode; testid?: string }) {
  return (
    <div className={`${KART} p-4`} data-testid={testid}>
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{etiket}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{deger}</p>
      {alt && <p className="mt-0.5 text-xs text-muted-foreground">{alt}</p>}
    </div>
  );
}
