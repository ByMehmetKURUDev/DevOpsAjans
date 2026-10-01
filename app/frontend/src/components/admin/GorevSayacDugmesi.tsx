import { useState } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { ZamanHatasi, sayacBaslat, sureGoster } from '@/lib/zamanTakibi';

/**
 * Faz 3Z — Kanban kartındaki küçük "başlat" düğmesi: bu görev için sunucu
 * sayacını başlatır (açık sayaç varsa durdurulur). Metinler `zamanTakibi` ek paketinde.
 */
export default function GorevSayacDugmesi({ projeId, gorevId, baslik }: { projeId: number; gorevId: number; baslik: string }) {
  const { t } = useTranslation();
  const [mesgul, setMesgul] = useState(false);

  const baslat = async () => {
    setMesgul(true);
    try {
      const y = await sayacBaslat({ proje_id: projeId, gorev_id: gorevId });
      toast.success(t('zamanTakibi.sayac.gorevdeBasladi', { baslik }));
      if (y.durdurulan) toast.message(t('zamanTakibi.sayac.oncekiDurdu', { sure: sureGoster(y.durdurulan.sure_dk) }));
    } catch (h) {
      const kod = h instanceof ZamanHatasi ? h.kod : 'genel';
      toast.error(t(`zamanTakibi.hata.${kod}`, { defaultValue: t('zamanTakibi.hata.genel') }));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void baslat()}
      disabled={mesgul}
      title={t('zamanTakibi.sayac.gorevdenBaslat')}
      aria-label={t('zamanTakibi.sayac.gorevdenBaslat')}
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-emerald-500/15 hover:text-emerald-300 disabled:opacity-50"
      data-testid={`gorev-sayac-${gorevId}`}
    >
      <Play className="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  );
}
