import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock, Plus } from 'lucide-react';

import { DUGME_ANA, KART } from '@/components/toplantilar/ortak';
import ToplantiIste from '@/components/toplantilar/ToplantiIste';

/**
 * Faz 6T — Projelerim'deki küçük "Toplantı iste" kartı: hesabın henüz toplantısı / talebi yokken Toplantılar
 * sekmesi gizli (düz menü kalabalıklaşmasın); talep gönderilince sekme açılır.
 */
export default function ToplantiIsteKarti({ onGonderildi }: { onGonderildi: () => void }) {
  const { t } = useTranslation();
  const [acik, setAcik] = useState(false);
  if (acik) return <div className="mb-4"><ToplantiIste onKapat={() => setAcik(false)} onGonderildi={onGonderildi} /></div>;
  return (
    <div className={`${KART} mb-4 flex flex-wrap items-center justify-between gap-3 p-4`} data-testid="toplanti-iste-karti">
      <p className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
        <CalendarClock className="h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
        {t('toplantilar.iste.kart')}
      </p>
      <button type="button" className={DUGME_ANA} onClick={() => setAcik(true)} data-toplanti-iste>
        <Plus className="h-4 w-4" aria-hidden="true" />
        {t('toplantilar.musteri.iste')}
      </button>
    </div>
  );
}
