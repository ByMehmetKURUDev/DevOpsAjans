import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/** CRM bileşenlerinin ortak parçaları (sınıf dili ProjeGorevleri ile aynı). */

export const SECIM =
  'h-9 w-full rounded-md border border-white/10 bg-white/5 px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

export const METIN_ALANI =
  'w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-purple-500/40';

export function Bekle() {
  return (
    <div className="flex items-center justify-center py-10 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" />
    </div>
  );
}

export function PuanRozeti({ puan, buyuk }: { puan: number; buyuk?: boolean }) {
  const { t } = useTranslation();
  const sinif =
    puan >= 60 ? 'bg-emerald-500/20 text-emerald-200' : puan >= 35 ? 'bg-amber-500/15 text-amber-200' : 'bg-white/10 text-foreground/70';
  return (
    <span
      className={`shrink-0 rounded-md font-semibold tabular-nums ${buyuk ? 'px-2.5 py-1 text-lg' : 'px-1.5 py-0.5 text-[11px]'} ${sinif}`}
      title={t('crm.puan.baslik')}
      data-crm-puan={puan}
    >
      {puan}
    </span>
  );
}

export function AlanEtiketi({ ad, zorunlu, children, tam }: { ad: string; zorunlu?: boolean; children: ReactNode; tam?: boolean }) {
  return (
    <label className={`block space-y-1 ${tam ? 'sm:col-span-2' : ''}`}>
      <span className="text-xs font-medium text-muted-foreground">
        {ad}
        {zorunlu ? ' *' : ''}
      </span>
      {children}
    </label>
  );
}
