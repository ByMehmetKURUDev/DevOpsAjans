import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

/** Faz 4W — Otomasyon bileşenlerinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const ALAN =
  'w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SECIM = ALAN + ' pe-8';
export const ROZET = 'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px]';
export const DUGME =
  'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 disabled:opacity-50';
export const ANA_DUGME = DUGME + ' bg-purple-600 text-white hover:bg-purple-500';
export const IKINCIL_DUGME = DUGME + ' border border-white/15 bg-white/[0.03] text-white hover:bg-white/10';

const DURUM_RENKLERI: Record<string, string> = {
  tamam: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  basarili: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  yapilacak: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  aktif: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  bekliyor: 'border-sky-400/30 bg-sky-500/10 text-sky-200',
  kosul_tutmadi: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  atlandi: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  atlanacak: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  pasif: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  hata: 'border-red-400/40 bg-red-500/10 text-red-200',
};

export function DurumRozeti({ durum, metin }: { durum: string; metin: string }) {
  return (
    <span className={`${ROZET} ${DURUM_RENKLERI[durum] || DURUM_RENKLERI.pasif}`} data-durum={durum}>
      {metin}
    </span>
  );
}

export function Etiket({ ad, children, ipucu, tam }: { ad: string; children: ReactNode; ipucu?: string; tam?: boolean }) {
  return (
    <label className={`block min-w-0 space-y-1 text-sm ${tam ? 'sm:col-span-2' : ''}`}>
      <span className="block text-xs font-medium text-muted-foreground">{ad}</span>
      {children}
      {ipucu && <span className="block text-[11px] text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

/** Sunucu özetindeki değerleri okunur biçimde (anahtar: değer). */
export function OzetSatirlari({ ozet }: { ozet?: Record<string, unknown> }) {
  const { t } = useTranslation();
  if (!ozet) return null;
  const satirlar = Object.entries(ozet).filter(([, v]) => v !== null && v !== undefined && v !== '');
  if (!satirlar.length) return null;
  return (
    <dl className="mt-1 grid gap-x-3 gap-y-0.5 text-xs sm:grid-cols-[max-content_1fr]">
      {satirlar.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{t(`otomasyon.ozet.${k}`, { defaultValue: k })}</dt>
          <dd className="min-w-0 whitespace-pre-wrap break-words text-slate-200">
            {Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
