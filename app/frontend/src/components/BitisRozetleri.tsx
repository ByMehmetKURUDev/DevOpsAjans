import { CalendarClock, Globe, Lock, Server } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { bitisRengi, tarihBicimle, type Izleme } from '@/lib/siteBakim';

/**
 * Alan adı / SSL / hosting bitiş rozetleri: >30 gün yeşil, ≤30 sarı, ≤7 kırmızı.
 * Yönetici ve müşteri kartı ortak kullanıyor.
 */
export default function BitisRozetleri({ izleme, siteId }: { izleme: Izleme; siteId: number }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;

  const kalanMetni = (gun: number | null) => {
    if (gun === null) return t('siteBakim.rozet.yok');
    if (gun < 0) return t('siteBakim.rozet.gecti', { sayi: Math.abs(gun) });
    if (gun === 0) return t('siteBakim.rozet.bugun');
    return t('siteBakim.rozet.kalan', { sayi: gun });
  };

  const rozetler = [
    { tur: 'alan', ikon: Globe, bitis: izleme.alan_bitis, kalan: izleme.alan_kalan },
    { tur: 'ssl', ikon: Lock, bitis: izleme.ssl_bitis, kalan: izleme.ssl_kalan },
    { tur: 'hosting', ikon: Server, bitis: izleme.hosting_bitis, kalan: izleme.hosting_kalan },
  ] as const;

  return (
    <div className="flex flex-wrap gap-1.5">
      {rozetler.map(({ tur, ikon: Ikon, bitis, kalan }) => (
        <span
          key={tur}
          data-testid={`bitis-${tur}-${siteId}`}
          title={bitis ? tarihBicimle(bitis, dil) : undefined}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${bitisRengi(kalan)}`}
        >
          <Ikon className="h-3 w-3" aria-hidden="true" />
          <span className="font-medium">{t(`siteBakim.rozet.${tur}`)}</span>
          <span className="opacity-90">{kalanMetni(kalan)}</span>
        </span>
      ))}
      {izleme.alan_bitis_kaynak === null && izleme.alan_rdap_hata === 'desteklenmiyor' && (
        <span className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-muted-foreground">
          <CalendarClock className="h-3 w-3" aria-hidden="true" />
          {t('siteBakim.bilgi.rdapDesteklenmiyor')}
        </span>
      )}
    </div>
  );
}
