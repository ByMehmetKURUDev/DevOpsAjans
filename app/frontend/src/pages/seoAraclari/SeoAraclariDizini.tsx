import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';

import { SEO_ARACLARI, seoAraclariYolu } from '../../../prerender/seo-araclari-veri.js';
import { PAGE_SEO_KEYS } from '../../../prerender/site.js';
import { AracKarti, SiteAnaliziCagrisi, Sss, dizi, paneldenSeo, useAracDili, useSayfaBasi } from './ortak';

/**
 * Ücretsiz SEO araçları dizini (`/seo-araclari`, 7 dil, prerender) — Faz 4S.
 *
 * Üst menüde YOK; alt bilgiden, Kaynaklar ve Site analizi sayfalarından
 * bağlantı var. SSS `<details>` ile; FAQPage JSON-LD aynı metinden (prerender).
 */
export default function SeoAraclariDizini() {
  const { t } = useTranslation();
  const dil = useAracDili();

  useSayfaBasi({
    baslik: paneldenSeo(PAGE_SEO_KEYS.seoAraclari.title, dil, t('seoAraclari.seo.baslik')),
    aciklama: paneldenSeo(PAGE_SEO_KEYS.seoAraclari.description, dil, t('seoAraclari.seo.aciklama')),
    yol: seoAraclariYolu(dil),
    diller: (d) => seoAraclariYolu(d),
  });

  const nedenler = dizi<string>(t('seoAraclari.dizin.neden', { returnObjects: true }));
  const sorular = dizi<{ s: string; c: string }>(t('seoAraclari.dizin.sss', { returnObjects: true }));

  return (
    <div className="pt-32 pb-24" data-seo-araclari-dizini>
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <header className="mb-12 max-w-3xl">
          <p className="mb-4 text-xs uppercase tracking-[0.3em] text-purple-300">{t('seoAraclari.dizin.etiket')}</p>
          <h1 className="mb-5 text-4xl font-bold leading-tight sm:text-5xl">
            {t('seoAraclari.dizin.baslik1')} <span className="gradient-text">{t('seoAraclari.dizin.baslikVurgu')}</span>
          </h1>
          <p className="text-lg text-muted-foreground">{t('seoAraclari.dizin.giris')}</p>
        </header>

        <div className="cam-dongu grid gap-6 sm:grid-cols-2 lg:grid-cols-3" data-arac-listesi>
          {SEO_ARACLARI.map((a) => (
            <AracKarti key={a.slug} a={a} dil={dil} />
          ))}
        </div>

        <div className="mt-16 grid gap-10 lg:grid-cols-5">
          <section className="lg:col-span-2">
            <h2 className="mb-4 text-xl font-bold">{t('seoAraclari.dizin.nedenBaslik')}</h2>
            <ul className="space-y-3">
              {nedenler.map((n) => (
                <li key={n} className="flex gap-3">
                  <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" aria-hidden="true" />
                  <span className="min-w-0 text-sm leading-relaxed text-muted-foreground">{n}</span>
                </li>
              ))}
            </ul>
          </section>
          <div className="min-w-0 lg:col-span-3">
            <Sss sorular={sorular} baslik={t('seoAraclari.dizin.sssBaslik')} />
          </div>
        </div>

        <div className="mt-16">
          <SiteAnaliziCagrisi dil={dil} />
        </div>
      </div>
    </div>
  );
}
