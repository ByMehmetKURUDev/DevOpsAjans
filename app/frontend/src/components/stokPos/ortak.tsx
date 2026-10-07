import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Loader2, X } from 'lucide-react';

import { barkodCiz, svgYolu } from '@/lib/barkod';

/** Faz 6P — stok/POS panelinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const GIRDI =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[72px] w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
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

export const Yukleniyor = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
  </div>
);

export function Bos({ children }: { children: ReactNode }) {
  return <p className="py-10 text-center text-sm text-muted-foreground">{children}</p>;
}

/** Ortadaki pencere (mobilde tam ekrana yakın); Esc ve arka plana tık kapatır. */
export function Pencere({ baslik, onKapat, children, genis, testid }: { baslik: string; onKapat: () => void; children: ReactNode; genis?: boolean; testid?: string }) {
  const { t } = useTranslation();
  const kok = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const tus = (e: KeyboardEvent) => e.key === 'Escape' && onKapat();
    window.addEventListener('keydown', tus);
    const once = document.activeElement as HTMLElement | null;
    kok.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus();
    return () => {
      window.removeEventListener('keydown', tus);
      once?.focus?.();
    };
  }, [onKapat]);
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onKapat()}
    >
      <div
        ref={kok}
        role="dialog"
        aria-modal="true"
        aria-label={baslik}
        className={`max-h-[92vh] w-full overflow-y-auto rounded-t-2xl border border-white/10 bg-[#120b1f] p-4 text-white shadow-2xl sm:rounded-2xl sm:p-5 ${genis ? 'sm:max-w-3xl' : 'sm:max-w-lg'}`}
        data-testid={testid}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h3 className="text-lg font-semibold">{baslik}</h3>
          <button type="button" onClick={onKapat} className="rounded-md p-1 text-muted-foreground hover:bg-white/10 hover:text-white" aria-label={t('stokPos.kapat')}>
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}

/** SVG barkod (EAN-13/EAN-8/Code128) — `currentColor` ile çizilir. */
export function Barkod({ kod, yukseklik = 42, className, etiket }: { kod: string; yukseklik?: number; className?: string; etiket?: string }) {
  const c = barkodCiz(kod);
  return (
    <svg
      viewBox={`0 0 ${c.moduller.length} ${yukseklik}`}
      preserveAspectRatio="none"
      className={className}
      role="img"
      aria-label={etiket || kod}
      data-barkod={kod}
      data-barkod-turu={c.tur}
      shapeRendering="crispEdges"
    >
      <path d={svgYolu(c.moduller, yukseklik)} fill="currentColor" />
    </svg>
  );
}
