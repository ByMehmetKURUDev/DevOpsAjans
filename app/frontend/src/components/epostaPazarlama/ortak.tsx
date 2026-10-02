import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

/** Faz 5M — e-posta pazarlama panelinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const GIRDI =
  'h-10 w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SECIM =
  'h-10 w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[84px] w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const DIS_DUGME = 'gap-1.5 !bg-transparent border-white/20';

export function Alan({ etiket, ipucu, children, className }: { etiket: string; ipucu?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block min-w-0 text-sm ${className ?? ''}`}>
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      {children}
      {ipucu && <span className="mt-1 block text-xs text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

export function Anahtar({
  acik,
  onDegis,
  etiket,
  testid,
  devreDisi,
}: {
  acik: boolean;
  onDegis: (v: boolean) => void;
  etiket: ReactNode;
  testid?: string;
  devreDisi?: boolean;
}) {
  return (
    <label className={`flex cursor-pointer items-start gap-2 text-sm ${devreDisi ? 'opacity-50' : ''}`}>
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 accent-purple-500"
        checked={acik}
        disabled={devreDisi}
        onChange={(e) => onDegis(e.target.checked)}
        data-testid={testid}
      />
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

export const IZIN_RENGI: Record<string, string> = {
  izinli: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  izinsiz: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  bekliyor: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  reddetti: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
};

export const DURUM_RENGI: Record<string, string> = {
  taslak: 'border-white/15 bg-white/[0.05] text-white/80',
  zamanlandi: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  gonderiliyor: 'border-purple-400/30 bg-purple-400/10 text-purple-200',
  ab_test: 'border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-200',
  duraklatildi: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  tamamlandi: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  iptal: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
};

export const Yukleniyor = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
  </div>
);

export function Bos({ children, testid }: { children: ReactNode; testid?: string }) {
  return (
    <p className="rounded-xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-muted-foreground" data-testid={testid}>
      {children}
    </p>
  );
}

export function sayiYaz(n: number | null | undefined, dil: string): string {
  if (n === null || n === undefined) return '∞';
  try {
    return new Intl.NumberFormat(dil).format(n);
  } catch {
    return String(n);
  }
}

/** Panoya kopyala (yedekli). */
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

/** `<input type="datetime-local">` değeri (yerel saat) → ISO (UTC). */
export function yereldenIso(deger: string): string | null {
  if (!deger) return null;
  const an = new Date(deger);
  return Number.isNaN(an.getTime()) ? null : an.toISOString();
}

export function isodanYerel(iso: string | null | undefined): string {
  if (!iso) return '';
  const an = new Date(iso);
  if (Number.isNaN(an.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${an.getFullYear()}-${p(an.getMonth() + 1)}-${p(an.getDate())}T${p(an.getHours())}:${p(an.getMinutes())}`;
}
