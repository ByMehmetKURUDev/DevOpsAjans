import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, Clock, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import SiteRaporGorunumu from '@/components/SiteRaporGorunumu';
import { SiteAnaliziHatasi, raporGetir, type TamRapor } from '@/lib/siteAnalizi';
import { DEFAULT_LANGUAGE, LANGUAGE_CODES, localizedPath } from '../../prerender/site.js';

/**
 * Tam site analiz raporu: `/rapor/<jeton>`.
 *
 * Bağlantı e-postayla gidiyor; oturum istemiyor. Her jeton tek bir
 * analize ait, 30 gün geçerli. Prerender listesinde yok ve çalışma
 * anında noindex veriliyor — bağlantı bir yerde paylaşılırsa arama
 * sonuçlarına düşmesin (ödeme sayfasıyla aynı desen).
 *
 * Süresi dolmuş bağlantı (410) hata gibi değil, "yeniden analiz et"
 * çağrısıyla gösteriliyor.
 */
export default function SiteRaporu() {
  const { jeton } = useParams<{ jeton: string }>();
  const { t, i18n } = useTranslation();
  const dil = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : DEFAULT_LANGUAGE;
  const analizYolu = localizedPath(dil, 'siteAnalysis');
  const [rapor, setRapor] = useState<TamRapor | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<SiteAnaliziHatasi | null>(null);

  useEffect(() => {
    const etiket = document.createElement('meta');
    etiket.name = 'robots';
    etiket.content = 'noindex, nofollow';
    document.head.appendChild(etiket);
    return () => {
      etiket.remove();
    };
  }, []);

  useEffect(() => {
    if (!jeton) return;
    let iptal = false;
    setYukleniyor(true);
    raporGetir(jeton)
      .then((r) => {
        if (!iptal) setRapor(r);
      })
      .catch((h) => {
        if (!iptal) setHata(h instanceof SiteAnaliziHatasi ? h : new SiteAnaliziHatasi(0, 'genel'));
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, [jeton]);

  return (
    <div className="pt-32 pb-24">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        {yukleniyor ? (
          <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
          </div>
        ) : hata ? (
          <div className="cam-kart mx-auto max-w-xl rounded-3xl border border-white/10 bg-white/[0.03] p-8 text-center">
            {hata.durum === 410 ? (
              <Clock className="mx-auto mb-3 h-10 w-10 text-amber-300" aria-hidden="true" />
            ) : (
              <AlertCircle className="mx-auto mb-3 h-10 w-10 text-red-300" aria-hidden="true" />
            )}
            <h1 className="text-xl font-semibold">
              {hata.durum === 410 ? t('siteAnalizi.rapor.sureDoldu') : t('siteAnalizi.rapor.bulunamadi')}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {hata.durum === 410
                ? t('siteAnalizi.rapor.sureDolduAciklama')
                : hata.durum === 404
                  ? t('siteAnalizi.rapor.bulunamadiAciklama')
                  : t('siteAnalizi.hata.genel')}
            </p>
            <Button asChild className="mt-6">
              <Link to={analizYolu}>{t('siteAnalizi.rapor.yenidenAnaliz')}</Link>
            </Button>
          </div>
        ) : rapor ? (
          <>
            <h1 className="sr-only">
              {t('siteAnalizi.rapor.baslik')} — {rapor.alan_adi}
            </h1>
            <SiteRaporGorunumu rapor={rapor} yazdirilabilir />
            <div className="yazdirma mt-10 flex flex-wrap justify-center gap-3">
              <Button asChild>
                <Link to={localizedPath(dil, 'contact')}>{t('siteAnalizi.teklif.teklifAl')}</Link>
              </Button>
              <Button asChild variant="outline">
                <Link to={analizYolu}>{t('siteAnalizi.yeniAnaliz')}</Link>
              </Button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
