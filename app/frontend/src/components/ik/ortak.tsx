import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Info, Loader2, X } from 'lucide-react';

import type { Uyari } from '@/lib/ik';

/** Faz 6I — İK panelinin ortak küçük parçaları (mevcut sınıf dili: `cam-kart`, mor vurgu). */

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

/** "Bilgilendirme amaçlıdır, hukuki danışmanlık değildir" notu. */
export function YasalNot({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <p className="flex items-start gap-2 rounded-xl border border-sky-400/25 bg-sky-500/10 p-3 text-xs text-sky-100" data-testid="ik-yasal-not">
      <Info className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
      <span>{children ?? t('ik.yasalNot')}</span>
    </p>
  );
}

/** Uyarı listesi (engellemez). */
export function Uyarilar({ uyarilar, dil, adlar }: { uyarilar: Uyari[]; dil: string; adlar?: Record<number, string> }) {
  const { t } = useTranslation();
  if (!uyarilar.length) return null;
  return (
    <ul className="space-y-1.5" data-testid="ik-uyarilar">
      {uyarilar.map((u, i) => (
        <li key={i} className="flex items-start gap-2 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden="true" />
          <span>{uyariMetni(t, u, dil, adlar)}</span>
        </li>
      ))}
    </ul>
  );
}

export function uyariMetni(t: (k: string, o?: Record<string, unknown>) => string, u: Uyari, dil: string, adlar?: Record<number, string>): string {
  const ad = typeof u.personel_id === 'number' && adlar ? adlar[u.personel_id] : undefined;
  const on = ad ? `${ad}: ` : '';
  const sayi = (x: unknown) => {
    try {
      return new Intl.NumberFormat(dil === 'ar' ? 'ar-u-nu-latn' : dil, { maximumFractionDigits: 1 }).format(Number(x));
    } catch {
      return String(x);
    }
  };
  switch (u.tur) {
    case 'cakisan_talep':
      return t('ik.uyari.cakisan_talep', { tur: t(`ik.tur.${String(u.izin_turu)}`), durum: t(`ik.durum.${String(u.durum)}`) });
    case 'bakiye_yetersiz':
      return t('ik.uyari.bakiye_yetersiz', { kalan: sayi(u.kalan), istenen: sayi(u.istenen) });
    case 'yasal_sure_asildi':
      return t(u.birim === 'takvim' ? 'ik.uyari.yasal_takvim' : 'ik.uyari.yasal_is_gunu', { yasal: sayi(u.yasal), istenen: sayi(u.istenen) });
    case 'calisma_gunu_yok':
      return t('ik.uyari.calisma_gunu_yok');
    case 'personel_ayrildi':
      return t('ik.uyari.personel_ayrildi');
    case 'izinli':
      return on + t('ik.uyari.izinli', { tur: t(`ik.tur.${String(u.izin_turu)}`) });
    case 'cakisma':
      return on + t('ik.uyari.cakisma');
    case 'dinlenme':
      return on + t('ik.uyari.dinlenme', { saat: sayi(u.saat), enAz: sayi(u.en_az) });
    case 'haftalik':
      return on + t('ik.uyari.haftalik', { saat: sayi(u.saat), enCok: sayi(u.en_cok) });
    default:
      return on + t('ik.uyari.genel');
  }
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
          <button type="button" onClick={onKapat} className="rounded-md p-1 text-muted-foreground hover:bg-white/10 hover:text-white" aria-label={t('ik.kapat')}>
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
      data-ik-bolum={testid}
    >
      {children}
    </button>
  );
}
