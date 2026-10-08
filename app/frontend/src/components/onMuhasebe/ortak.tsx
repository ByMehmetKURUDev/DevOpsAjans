import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Info, Loader2, X } from 'lucide-react';

import { KOVALAR, para, type YasOzeti } from '@/lib/onMuhasebe';

/** Faz 6M — ön muhasebe panelinin ortak küçük parçaları (mevcut sınıf dili: `cam-kart`, mor vurgu). */

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
    <p className="text-sm text-red-300" role="alert" data-testid="mh-hata">
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
        className={`max-h-[92vh] w-full overflow-y-auto rounded-t-2xl border border-white/10 bg-[#120b1f] p-4 text-white shadow-2xl sm:rounded-2xl sm:p-5 ${genis ? 'sm:max-w-3xl' : 'sm:max-w-lg'}`}
        data-testid={testid}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h3 className="text-lg font-semibold">{baslik}</h3>
          <button type="button" onClick={onKapat} className="rounded-md p-1 text-muted-foreground hover:bg-white/10 hover:text-white" aria-label={t('onMuhasebe.ortak.kapat')}>
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
      data-mh-bolum={testid}
    >
      {children}
    </button>
  );
}

/** Küçük sekme düğmeleri (raporlar, süzgeçler). */
export function Hap({ secili, onClick, children, testid }: { secili: boolean; onClick: () => void; children: ReactNode; testid?: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={secili}
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-xs ${secili ? 'border-purple-400/60 bg-purple-500/20 text-white' : 'border-white/10 text-muted-foreground hover:text-white'}`}
      data-mh-hap={testid}
    >
      {children}
    </button>
  );
}

/** İşaretli tutar (artı yeşil, eksi kırmızı). */
export function Tutar({ deger, metin, notr, testid }: { deger: number; metin: string; notr?: boolean; testid?: string }) {
  const renk = notr || deger === 0 ? 'text-white' : deger > 0 ? 'text-emerald-300' : 'text-rose-300';
  return (
    <span className={`whitespace-nowrap font-medium tabular-nums ${renk}`} data-testid={testid}>
      {metin}
    </span>
  );
}

/** Yaşlandırma kovaları (vadesi gelmemiş, 0–30, 31–60, 61–90, 90+). */
export function KovaTablosu({ y, pb, baslik }: { y: YasOzeti; pb: string; baslik: string }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  return (
    <div>
      <h4 className="mb-1 text-sm font-semibold">{baslik}</h4>
      <div className="grid grid-cols-2 gap-1 text-xs sm:grid-cols-5">
        {KOVALAR.map((k) => (
          <div key={k} className={`rounded-lg border p-2 ${k === '90_ustu' && y.kovalar[k] ? 'border-rose-400/40 bg-rose-500/10' : 'border-white/10'}`} data-kova={k}>
            <p className="text-muted-foreground">{t(`onMuhasebe.kova.${k}`)}</p>
            <p className="font-semibold tabular-nums">{para(y.kovalar[k] || 0, pb, dil)}</p>
          </div>
        ))}
      </div>
      {y.en_eski_gun !== null && y.en_eski_gun > 0 && <p className="mt-1 text-xs text-amber-200">{t('onMuhasebe.cari.enEski', { gun: y.en_eski_gun })}</p>}
    </div>
  );
}
