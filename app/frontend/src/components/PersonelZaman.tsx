import { Suspense, lazy } from 'react';
import { Loader2, Timer } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const ZamanTakibi = lazy(() => import('@/components/admin/ZamanTakibi'));

/**
 * Faz 3Z — ajans personelinin (yönetici olmayan ekip üyesi) kendi zaman
 * kayıtları: müşteri panelinin üstünde katlanır bölüm. Yalnız `/zaman/ben`
 * "personel" dediğinde çizilir (ClientPanel); metinler `zamanTakibi` ek paketinde.
 */
export default function PersonelZaman() {
  const { t } = useTranslation();
  return (
    <details className="cam-kart mb-6 rounded-2xl border border-purple-500/30 bg-white/[0.03] p-4 sm:p-5" data-testid="personel-zaman">
      <summary className="flex cursor-pointer items-center gap-2 font-semibold text-purple-200">
        <Timer className="h-4 w-4" aria-hidden="true" /> {t('zamanTakibi.personel.baslik')}
      </summary>
      <div className="mt-4">
        <Suspense fallback={<Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}>
          <ZamanTakibi yonetici={false} />
        </Suspense>
      </div>
    </details>
  );
}
