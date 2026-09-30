import { useEffect, useState } from 'react';
import { Cookie } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { RIZA_OLAYI, rizayiOku, rizayiYaz } from '@/lib/riza';

/**
 * Ölçüm ve reklam rızası bandı.
 *
 * Ziyaretçi cevaplayana kadar GA, Google Ads ve Meta Pixel yüklenmiyor.
 * "Reddet" tuşu "Kabul et" ile aynı görünürlükte: reddetmeyi zorlaştıran
 * bir bant, olmayan bandın hukuken daha kötüsü.
 *
 * Bant prerender edilen HTML'de görünmüyor (ilk çizimde `null`), çünkü
 * kararın `localStorage`'dan okunması gerekiyor ve sunucuda böyle bir
 * şey yok. Sayfa oturduktan sonra beliriyor; içeriğin önünü kapatmıyor,
 * alt kenarda duruyor.
 */
export default function RizaBandi() {
  const { t } = useTranslation();
  const [gorunur, setGorunur] = useState(false);

  useEffect(() => {
    const tazele = () => setGorunur(rizayiOku() === 'sorulmadi');
    tazele();
    // Alt bilgideki "Çerez tercihleri" bağlantısı kararı sıfırlayınca
    // bandın yeniden çıkması gerekiyor.
    window.addEventListener(RIZA_OLAYI, tazele);
    return () => window.removeEventListener(RIZA_OLAYI, tazele);
  }, []);

  if (!gorunur) return null;

  return (
    <div
      role="region"
      aria-label={t('riza.baslik')}
      className="fixed inset-x-0 bottom-0 z-[60] border-t border-white/12 bg-background/95 px-4 py-4 backdrop-blur-xl sm:px-6"
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-4 sm:flex-row sm:items-center">
        <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-primary/15">
          <Cookie className="h-4 w-4 text-primary" aria-hidden="true" />
        </span>

        <p className="flex-1 text-sm leading-relaxed text-muted-foreground">
          {t('riza.metin')}{' '}
          <Link to="/contact" className="text-primary underline underline-offset-2">
            {t('riza.detay')}
          </Link>
        </p>

        <div className="flex flex-none gap-2">
          <Button
            onClick={() => rizayiYaz('red')}
            variant="outline"
            className="h-10 border-white/20 !bg-transparent !hover:bg-transparent"
          >
            {t('riza.reddet')}
          </Button>
          <Button
            onClick={() => rizayiYaz('kabul')}
            className="h-10 border-0 bg-primary text-background"
          >
            {t('riza.kabul')}
          </Button>
        </div>
      </div>
    </div>
  );
}
