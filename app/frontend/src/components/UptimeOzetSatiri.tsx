import { Activity } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { tarihBicimle, yuzdeBicimle, type UptimeOzeti } from '@/lib/siteBakim';

const GUNCEL_RENK: Record<string, string> = {
  calisiyor: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  kesinti: 'border-red-400/40 bg-red-500/15 text-red-200',
  bilinmiyor: 'border-white/10 bg-white/[0.04] text-muted-foreground',
};

/** Güncel durum + 24s/7g/30g erişilebilirlik + son kesinti (tek satır, sarılabilir). */
export default function UptimeOzetSatiri({ ozet, siteId }: { ozet: UptimeOzeti; siteId: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const son = ozet.kesintiler[0];

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
      <span
        data-testid={`uptime-guncel-${siteId}`}
        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${GUNCEL_RENK[ozet.guncel] ?? GUNCEL_RENK.bilinmiyor}`}
      >
        <Activity className="h-3 w-3" aria-hidden="true" />
        {t(`siteBakim.guncel.${ozet.guncel}`)}
      </span>
      {(
        [
          ['son24', ozet.oran_24s, '24s'],
          ['son7', ozet.oran_7g, '7g'],
          ['son30', ozet.oran_30g, '30g'],
        ] as const
      ).map(([anahtar, oran, kisa]) => (
        <span key={anahtar} className="text-muted-foreground">
          {t(`siteBakim.uptime.${anahtar}`)}{' '}
          <span className="font-semibold text-foreground" data-testid={`uptime-oran-${kisa}-${siteId}`}>
            {yuzdeBicimle(oran, dil)}
          </span>
        </span>
      ))}
      <span className="text-muted-foreground" data-testid={`uptime-son-kesinti-${siteId}`}>
        {t('siteBakim.uptime.sonKesinti')}:{' '}
        {son ? (
          <>
            {tarihBicimle(son.baslangic, dil, true)}
            {' · '}
            {son.bitis ? t('siteBakim.uptime.sureDk', { sayi: son.sure_dk ?? 0 }) : t('siteBakim.uptime.devamEdiyor')}
          </>
        ) : (
          t('siteBakim.uptime.kesintiYok')
        )}
      </span>
    </div>
  );
}
