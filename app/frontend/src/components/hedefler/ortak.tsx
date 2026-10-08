import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Info, Loader2, X } from 'lucide-react';

import { DURUM_RENGI, yuzde, type IlerlemeDurumu } from '@/lib/okr';

/** Faz 6O — Hedefler panelinin ortak küçük parçaları (mevcut sınıf dili: `cam-kart`, mor vurgu; üç görünümde okunur). */

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
    <label className={`block min-w-0 text-sm ${className ?? ''}`}>
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      {children}
      {ipucu && <span className="mt-1 block text-xs text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

export function Rozet({ children, renk = 'border-white/10 bg-white/[0.05] text-muted-foreground', testid }: { children: ReactNode; renk?: string; testid?: string }) {
  return (
    <span className={`inline-flex max-w-full items-center gap-1 truncate whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${renk}`} data-testid={testid}>
      {children}
    </span>
  );
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

export function Not({ children, testid }: { children: ReactNode; testid?: string }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-sky-400/25 bg-sky-500/10 p-3 text-xs text-sky-100" data-testid={testid}>
      <Info className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

export function HataSatiri({ hata }: { hata: string | null }) {
  if (!hata) return null;
  return (
    <p className="text-sm text-red-300" role="alert" data-testid="okr-hata">
      {hata}
    </p>
  );
}

/** Ortadaki pencere (mobilde alttan); Esc ve arka plana tık kapatır. */
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
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onKapat()}>
      <div
        ref={kok}
        role="dialog"
        aria-modal="true"
        aria-label={baslik}
        className={`max-h-[92vh] w-full overflow-y-auto overflow-x-hidden rounded-t-2xl border border-white/10 bg-[#120b1f] p-4 text-white shadow-2xl sm:rounded-2xl sm:p-5 ${genis ? 'sm:max-w-3xl' : 'sm:max-w-lg'}`}
        data-testid={testid}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h3 className="min-w-0 break-words text-lg font-semibold">{baslik}</h3>
          <button type="button" onClick={onKapat} className="flex-none rounded-md p-1 text-muted-foreground hover:bg-white/10 hover:text-white" aria-label={t('hedefler.ortak.kapat')}>
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body
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
      data-okr-bolum={testid}
    >
      {children}
    </button>
  );
}

/**
 * İlerleme çubuğu: dolu kısım ilerleme (renk durumdan), ince dikey çizgi beklenen ilerleme. Erişilebilir `progressbar`.
 */
export function IlerlemeCubugu({ ilerleme, beklenen, durum, etiket, kucuk, testid }: {
  ilerleme: number | null;
  beklenen?: number | null;
  durum?: IlerlemeDurumu | null;
  etiket: string;
  kucuk?: boolean;
  testid?: string;
}) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const deger = Math.max(0, Math.min(1, ilerleme ?? 0));
  const renk = durum ? DURUM_RENGI[durum] : 'bg-purple-400';
  return (
    <div className="min-w-0" data-testid={testid} data-ilerleme={ilerleme === null ? '' : Math.round(deger * 100)}>
      <div
        className={`relative w-full overflow-hidden rounded-full bg-white/10 ${kucuk ? 'h-1.5' : 'h-2.5'}`}
        role="progressbar"
        aria-label={etiket}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(deger * 100)}
        aria-valuetext={ilerleme === null ? t('hedefler.ortak.olcumYok') : yuzde(deger, dil)}
      >
        <div className={`absolute inset-y-0 start-0 rounded-full ${renk} transition-[width] duration-500`} style={{ width: `${deger * 100}%` }} />
        {beklenen !== undefined && beklenen !== null && beklenen > 0 && beklenen < 1 && (
          <div className="absolute inset-y-0 w-0.5 bg-white/70" style={{ insetInlineStart: `calc(${beklenen * 100}% - 1px)` }} aria-hidden="true" />
        )}
      </div>
    </div>
  );
}
