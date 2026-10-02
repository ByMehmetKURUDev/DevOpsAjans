import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

/** Faz 5A — AI asistan panelinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[84px] w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const DIS_DUGME = 'gap-1.5 !bg-transparent border-white/20';

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
    <label className={`flex cursor-pointer items-center gap-2 text-sm ${devreDisi ? 'opacity-50' : ''}`}>
      <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={acik} disabled={devreDisi} onChange={(e) => onDegis(e.target.checked)} data-testid={testid} />
      <span>{etiket}</span>
    </label>
  );
}

export function Rozet({ children, renk = 'border-white/10 bg-white/[0.05] text-muted-foreground', testid }: { children: ReactNode; renk?: string; testid?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${renk}`} data-testid={testid}>
      {children}
    </span>
  );
}

export const Yukleniyor = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
  </div>
);

export function sayiYaz(n: number, dil: string, ondalik = 0): string {
  try {
    return new Intl.NumberFormat(dil, { maximumFractionDigits: ondalik }).format(n);
  } catch {
    return String(n);
  }
}

export function tarihYaz(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export async function kopyala(metin: string, basari: string, hata: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(metin);
      toast.success(basari);
      return;
    }
  } catch {
    /* yedeğe düş */
  }
  toast.error(hata);
}

/** Satır satır liste (boşlar atılır). */
export function satirlar(metin: string): string[] {
  return metin
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}
