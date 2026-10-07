import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Info, ShieldAlert } from 'lucide-react';

import type { Catisma } from '@/lib/hukuk';

/** Faz 6H — hukuk sekmesinin küçük ortak parçaları (randevu/eğitim sınıf dili: `cam-kart`). */

export { KART, SECIM, METIN_ALANI, Alan, Anahtar, Rozet, Yukleniyor, kopyala } from '@/components/randevu/ortak';

export const GIRDI =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';

export const DURUM_RENGI: Record<string, string> = {
  acik: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  beklemede: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  kapandi: 'border-zinc-400/30 bg-zinc-500/10 text-zinc-300',
};

export const OLAY_RENGI: Record<string, string> = {
  durusma: 'border-sky-400/40 bg-sky-500/15 text-sky-100',
  kesif: 'border-violet-400/40 bg-violet-500/15 text-violet-100',
  bilirkisi: 'border-indigo-400/40 bg-indigo-500/15 text-indigo-100',
  kesin_sure: 'border-rose-400/50 bg-rose-500/20 text-rose-100',
  gorev: 'border-white/15 bg-white/[0.06] text-white/80',
};

export function SekmeDugmesi({ secili, onClick, children, testid }: { secili: boolean; onClick: () => void; children: ReactNode; testid?: string }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={secili}
      onClick={onClick}
      className={`flex flex-none items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-colors ${
        secili ? 'bg-blue-500/20 text-white' : 'text-muted-foreground hover:bg-white/[0.05] hover:text-white'
      }`}
      data-hukuk-alt={testid}
    >
      {children}
    </button>
  );
}

/** "Bilgilendirme amaçlıdır…" ve benzeri açık notlar. */
export function Not({ children, tur = 'bilgi', testid }: { children: ReactNode; tur?: 'bilgi' | 'uyari'; testid?: string }) {
  const Ikon = tur === 'uyari' ? AlertTriangle : Info;
  return (
    <p
      className={`flex items-start gap-2 rounded-xl border p-3 text-xs leading-relaxed ${
        tur === 'uyari' ? 'border-amber-400/30 bg-amber-500/10 text-amber-100' : 'border-sky-400/20 bg-sky-500/[0.07] text-sky-100'
      }`}
      data-testid={testid}
    >
      <Ikon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

/** Çıkar çatışması uyarı listesi (engelleme yok). */
export function CatismaListesi({ items, testid = 'hukuk-catisma' }: { items: Catisma[] | null; testid?: string }) {
  const { t } = useTranslation();
  if (items === null) return null;
  if (items.length === 0) {
    return (
      <p className="text-xs text-emerald-300" data-testid={`${testid}-yok`}>
        {t('hukuk.catisma.yok')}
      </p>
    );
  }
  return (
    <div className="rounded-xl border border-rose-400/40 bg-rose-500/10 p-3 text-sm" role="alert" data-testid={testid} data-sayi={items.length}>
      <p className="mb-1 flex items-center gap-1.5 font-semibold text-rose-100">
        <ShieldAlert className="h-4 w-4" aria-hidden="true" />
        {t('hukuk.catisma.baslik')}
      </p>
      <p className="mb-2 text-xs text-rose-100/80">{t('hukuk.catisma.aciklama')}</p>
      <ul className="space-y-1">
        {items.map((c, i) => (
          <li key={i} className="text-xs text-rose-50" data-onem={c.onem}>
            <span className={`me-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${c.onem === 'catisma' ? 'bg-rose-500/40' : 'bg-white/10'}`}>
              {t(`hukuk.catisma.onem.${c.onem}`)}
            </span>
            {c.gizli
              ? t('hukuk.catisma.gizli')
              : t('hukuk.catisma.satir', { ad: c.ad || '', rol: t(`hukuk.catisma.rol.${c.rol}`), eslesme: t(`hukuk.catisma.eslesme.${c.eslesme}`) })}
            {!c.gizli && c.dosya_baslik && <span className="text-rose-100/70"> · {t('hukuk.catisma.dosyada', { dosya: c.dosya_baslik })}</span>}
            {c.aranan && <span className="text-rose-100/70"> · {c.aranan}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
