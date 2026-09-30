import {
  Activity,
  Bot,
  ExternalLink,
  FileSearch,
  Gauge,
  Map as MapIcon,
  Monitor,
  ScanSearch,
  Search,
  Smartphone,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { SITE_URL } from '../../../prerender/site.js';

/**
 * Site sağlığı kısayolları.
 *
 * GTmetrix, PageSpeed/Lighthouse ve Search Console'un siteye koyulacak
 * bir "entegrasyonu" yok -- hiçbiri sayfaya etiket istemiyor, hepsi
 * dışarıdan siteyi ölçüyor. O yüzden burada yapılan şey dürüst olanı:
 * adresi hazır, tek tıkla açılan bağlantılar. Panelde "bağlı" yazan ama
 * arkasında hiçbir şey olmayan bir kutu koymaktan iyi.
 *
 * Search Console'un doğrulama etiketi ayrı: o gerçekten siteye giriyor
 * (Ayarlar → Entegrasyonlar → Google doğrulama kodu).
 */

export default function SiteSagligi() {
  const { t } = useTranslation();
  const site = SITE_URL;
  const kodlu = encodeURIComponent(site);

  const baglantilar = [
    {
      anahtar: 'psiMobil',
      ikon: Smartphone,
      etiket: t('siteSagligi.psiMobil'),
      aciklama: t('siteSagligi.psiMobilDesc'),
      url: `https://pagespeed.web.dev/analysis?url=${kodlu}&form_factor=mobile`,
    },
    {
      anahtar: 'psiMasaustu',
      ikon: Monitor,
      etiket: t('siteSagligi.psiMasaustu'),
      aciklama: t('siteSagligi.psiMasaustuDesc'),
      url: `https://pagespeed.web.dev/analysis?url=${kodlu}&form_factor=desktop`,
    },
    {
      anahtar: 'gtmetrix',
      ikon: Activity,
      etiket: t('siteSagligi.gtmetrix'),
      aciklama: t('siteSagligi.gtmetrixDesc'),
      url: 'https://gtmetrix.com/',
    },
    {
      anahtar: 'gsc',
      ikon: Search,
      etiket: t('siteSagligi.gsc'),
      aciklama: t('siteSagligi.gscDesc'),
      url: `https://search.google.com/search-console?resource_id=${kodlu}`,
    },
    {
      anahtar: 'crawlStats',
      ikon: Bot,
      etiket: t('siteSagligi.crawlStats'),
      aciklama: t('siteSagligi.crawlStatsDesc'),
      url: `https://search.google.com/search-console/settings/crawl-stats?resource_id=${kodlu}`,
    },
    {
      anahtar: 'urlInspect',
      ikon: ScanSearch,
      etiket: t('siteSagligi.urlInspect'),
      aciklama: t('siteSagligi.urlInspectDesc'),
      url: `https://search.google.com/search-console/inspect?resource_id=${kodlu}&id=${kodlu}`,
    },
    {
      anahtar: 'sitemap',
      ikon: MapIcon,
      etiket: t('siteSagligi.sitemap'),
      aciklama: t('siteSagligi.sitemapDesc'),
      url: `${site}/sitemap.xml`,
    },
    {
      anahtar: 'robots',
      ikon: FileSearch,
      etiket: t('siteSagligi.robots'),
      aciklama: t('siteSagligi.robotsDesc'),
      url: `${site}/robots.txt`,
    },
  ];

  return (
    <div className="glass rounded-2xl p-5">
      <div className="mb-1 flex items-center gap-2">
        <Gauge className="h-4 w-4 text-purple-300" />
        <h3 className="text-sm font-semibold">{t('siteSagligi.baslik')}</h3>
      </div>
      <p className="mb-4 text-xs text-muted-foreground">{t('siteSagligi.aciklama')}</p>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {baglantilar.map(({ anahtar, ikon: Ikon, etiket, aciklama, url }) => (
          <a
            key={anahtar}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="group flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 transition-colors hover:border-purple-400/40"
          >
            <span className="mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-lg bg-white/5">
              <Ikon className="h-4 w-4 text-purple-300" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="flex items-center gap-1 text-sm font-semibold">
                {etiket}
                <ExternalLink
                  className="h-3 w-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                  aria-hidden="true"
                />
              </span>
              <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">
                {aciklama}
              </span>
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
