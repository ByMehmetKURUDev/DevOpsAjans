import React from 'react';
import { renderToString } from 'react-dom/server';
import { Route, Routes } from 'react-router-dom';
import { StaticRouter } from 'react-router-dom/server';
import { I18nextProvider } from 'react-i18next';

import i18n from '../src/i18n';
import en from '../src/i18n/en.json';
import de from '../src/i18n/de.json';
import ar from '../src/i18n/ar.json';
import ru from '../src/i18n/ru.json';
import zh from '../src/i18n/zh.json';
import hi from '../src/i18n/hi.json';
import tr from '../src/i18n/tr.json';

import Layout from '../src/components/Layout';
import LanguageGate from '../src/components/LanguageGate';
import Index from '../src/pages/Index';
import Services from '../src/pages/Services';
import Portfolio from '../src/pages/Portfolio';
import Marketplace from '../src/pages/Marketplace';
import Contact from '../src/pages/Contact';
import YolHaritasi from '../src/pages/YolHaritasi';
import SiteAnalizi from '../src/pages/SiteAnalizi';
import BlogIndexPage from '../src/pages/blog/BlogIndexPage';
import BlogPostPage from '../src/pages/blog/BlogPostPage';
import KaynaklarListesi from '../src/pages/kaynaklar/KaynaklarListesi';
import KaynakDetay from '../src/pages/kaynaklar/KaynakDetay';
import ModullerListesi from '../src/pages/moduller/ModullerListesi';
import ModulDetay from '../src/pages/moduller/ModulDetay';
import PaketDetay from '../src/pages/moduller/PaketDetay';
import Ortaklik from '../src/pages/Ortaklik';
import YasalSayfa from '../src/pages/yasal/YasalSayfa';
import SeoAraclariDizini from '../src/pages/seoAraclari/SeoAraclariDizini';
import SeoAracSayfasi from '../src/pages/seoAraclari/SeoAracSayfasi';
import { gomuluVeriyiAyarla } from '../src/lib/kaynaklar';
import { yasalVeriyiAyarla } from '../src/lib/yasal';
import { gomuluFiyatlariAyarla } from '../src/lib/modulVitrini';
import { extractFaq, getBlogPost, getPostSeoMeta } from '../src/lib/blog';
// Derleme verisi (canlı API ya da tohum dosyası) — vite.config `kaynakVeriEklentisi` sağlıyor.
import KAYNAK_VERISI from 'virtual:kaynaklar-veri';
import { KAYNAKLAR_SEO, kaynakBasligi, metaAciklama } from './kaynaklar-seo.js';
import { KAYNAK_DILLERI, detayVerisi, kaynakYolu, kaynakYolunuCoz, listeVerisi } from './kaynaklar-veri.js';
// Faz 4V: modül vitrini — yapı depodaki kopyadan (kayıttan üretilmiş), fiyat derlemede canlı uçtan
// (vite.config `vitrinFiyatEklentisi`; okunamazsa boş → fiyatsız sayfa, JSON-LD'de offers yok).
import VITRIN_YAPISI from './modul-vitrini-veri.json';
import VITRIN_FIYATLARI from 'virtual:modul-vitrini-fiyat';
import {
  MODUL_DILLERI,
  modulBul,
  modulFiyati,
  modulYolu,
  modulYolunuCoz,
  modullerYolu,
  olcekAdi,
  paketBul,
  paketYolu,
} from './moduller-veri.js';
import { loadPanelSettings, resolvePanelValue } from './settings.js';
import { yasalSeo } from './yasal-seo.js';
import { SEO_ARACLARI, SEO_ARAC_DILLERI, seoAracBul, seoAracYolu, seoAracYolunuCoz, seoAraclariYolu } from './seo-araclari-veri.js';
import { yasalAyarlariniYukle } from './yasal-yukle.js';
import {
  BLOG_INDEX_ROUTE,
  DEFAULT_LANGUAGE,
  ORGANIZATION_JSONLD,
  PAGE_SEO,
  PAGE_SEO_KEYS,
  SITE_NAME,
  SITE_OG_IMAGE,
  SITE_URL,
  YASAL_SAYFALAR,
  absoluteUrl,
  canonicalPathFor,
  getLanguage,
  localizedPath,
  resolveRoute,
} from './site.js';

const h = React.createElement;

/**
 * Diğer dillerin paketleri istemcide talep üzerine iniyor; prerender
 * senkron çalıştığı için hepsi burada baştan yükleniyor.
 */
const BUNDLES = { en, de, ar, ru, zh, hi };
for (const [code, resources] of Object.entries(BUNDLES)) {
  if (!i18n.hasResourceBundle(code, 'translation')) {
    i18n.addResourceBundle(code, 'translation', resources, true, true);
  }
}

/** Ek çeviri paketleri (src/i18n/ek) — istemcide sayfayla birlikte iniyor, burada hepsi baştan. */
const EK_PAKETLER = import.meta.glob('../src/i18n/ek/*/*.json', { eager: true });
for (const [yol, mod] of Object.entries(EK_PAKETLER)) {
  const dil = yol.split('/').pop().replace('.json', '');
  i18n.addResourceBundle(dil, 'translation', mod.default ?? mod, true, true);
}

/**
 * Sayfalar burada lazy() olmadan kuruluyor: renderToString Suspense'i
 * bekleyemediği için lazy bileşenler sunucuda yalnızca yükleme animasyonunu
 * basardı. İstemci tarafı (App.tsx) lazy yüklemeyi korumaya devam ediyor.
 *
 * Route yolları App.tsx ile aynı olmak zorunda; `scripts/check-routes.mjs`
 * her build'de ikisini karşılaştırıp ayrışırsa build'i durduruyor.
 */
function renderApp(url) {
  return renderToString(
    h(
      I18nextProvider,
      { i18n },
      h(
        StaticRouter,
        { location: url },
        h(
          Routes,
          null,
          h(
            Route,
            { element: h(Layout, null) },
            h(Route, { path: '/', element: h(Index, null) }),
            h(Route, { path: '/services', element: h(Services, null) }),
            h(Route, { path: '/portfolio', element: h(Portfolio, null) }),
            h(Route, { path: '/marketplace', element: h(Marketplace, null) }),
            h(Route, { path: '/contact', element: h(Contact, null) }),
            h(Route, { path: '/yol-haritasi', element: h(YolHaritasi, null) }),
            h(Route, { path: '/site-analizi', element: h(SiteAnalizi, null) }),
            h(Route, { path: '/blog', element: h(BlogIndexPage, null) }),
            h(Route, { path: '/blog/:slug', element: h(BlogPostPage, null) }),
            h(Route, { path: '/kaynaklar', element: h(KaynaklarListesi, null) }),
            h(Route, { path: '/kaynaklar/:slug', element: h(KaynakDetay, null) }),
            h(Route, { path: '/moduller', element: h(ModullerListesi, null) }),
            h(Route, { path: '/moduller/:slug', element: h(ModulDetay, null) }),
            h(Route, { path: '/moduller/paket/:slug', element: h(PaketDetay, null) }),
            h(Route, { path: '/seo-araclari', element: h(SeoAraclariDizini, null) }),
            h(Route, { path: '/seo-araclari/:slug', element: h(SeoAracSayfasi, null) }),
            h(Route, { path: '/ortaklik', element: h(Ortaklik, null) }),
            h(Route, { path: '/gizlilik', element: h(YasalSayfa, { sayfa: 'gizlilik' }) }),
            h(Route, { path: '/kullanim-kosullari', element: h(YasalSayfa, { sayfa: 'kullanimKosullari' }) }),
            h(Route, { path: '/cerez-politikasi', element: h(YasalSayfa, { sayfa: 'cerezPolitikasi' }) }),
          ),
          h(
            Route,
            { path: '/:lang', element: h(LanguageGate, null) },
            h(Route, { index: true, element: h(Index, null) }),
            h(Route, { path: 'services', element: h(Services, null) }),
            h(Route, { path: 'portfolio', element: h(Portfolio, null) }),
            h(Route, { path: 'marketplace', element: h(Marketplace, null) }),
            h(Route, { path: 'contact', element: h(Contact, null) }),
            h(Route, { path: 'yol-haritasi', element: h(YolHaritasi, null) }),
            h(Route, { path: 'site-analizi', element: h(SiteAnalizi, null) }),
            h(Route, { path: 'kaynaklar', element: h(KaynaklarListesi, null) }),
            h(Route, { path: 'kaynaklar/:slug', element: h(KaynakDetay, null) }),
            h(Route, { path: 'moduller', element: h(ModullerListesi, null) }),
            h(Route, { path: 'moduller/:slug', element: h(ModulDetay, null) }),
            h(Route, { path: 'moduller/paket/:slug', element: h(PaketDetay, null) }),
            h(Route, { path: 'seo-araclari', element: h(SeoAraclariDizini, null) }),
            h(Route, { path: 'seo-araclari/:slug', element: h(SeoAracSayfasi, null) }),
            h(Route, { path: 'ortaklik', element: h(Ortaklik, null) }),
            h(Route, { path: 'gizlilik', element: h(YasalSayfa, { sayfa: 'gizlilik' }) }),
            h(Route, { path: 'kullanim-kosullari', element: h(YasalSayfa, { sayfa: 'kullanimKosullari' }) }),
            h(Route, { path: 'cerez-politikasi', element: h(YasalSayfa, { sayfa: 'cerezPolitikasi' }) }),
          ),
        ),
      ),
    ),
  );
}

function getBlogSlug(url) {
  const path = canonicalPathFor(url.split('?')[0].split('#')[0]);
  if (!path.startsWith('/blog')) return null;
  const slug = path.slice('/blog'.length).replace(/^\/+/, '');
  return slug || null;
}

function meta(attribute, key, value) {
  if (!value) return null;
  return { type: 'meta', props: { [attribute]: key, content: value } };
}

/**
 * Ana sayfadaki SSS'in FAQPage karşılığı.
 *
 * Sorular ekranda görünen metinlerin ta kendisi (`tr.json` → `sss`), ayrı
 * bir liste tutulmuyor: bölümde soru değişince arama sonuçlarındaki
 * karşılığı da değişiyor. Google yalnızca sayfada görünen içeriğin
 * işaretlenmesini istiyor, bu yüzden tek kaynak olması önemli.
 */
function faqJsonLd() {
  const sss = tr.sss || {};
  const girisler = [];
  for (let i = 1; i <= 12; i++) {
    const kayit = sss[`s${i}`];
    if (!kayit || !kayit.soru || !kayit.cevap) break;
    girisler.push({
      '@type': 'Question',
      name: kayit.soru,
      acceptedAnswer: { '@type': 'Answer', text: kayit.cevap },
    });
  }
  if (girisler.length === 0) return null;
  return { '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: girisler };
}

function jsonLd(data) {
  return {
    type: 'script',
    props: { type: 'application/ld+json', children: JSON.stringify(data) },
  };
}

/** `</script>` gövdeyi kapatmasın: JSON içinde `<` kaçışlı (JSON olarak hâlâ geçerli). */
function guvenliJson(data) {
  return JSON.stringify(data).replace(/</g, '\\u003c');
}

const YAYINCI = {
  '@type': 'Organization',
  name: SITE_NAME,
  url: `${SITE_URL}/`,
  logo: { '@type': 'ImageObject', url: SITE_OG_IMAGE },
};

/** Kaynak sayfasının verisi: hem HTML bununla çiziliyor hem sayfaya gömülüyor. */
function kaynakGomuluVerisi(url, { dil, slug }) {
  const yol = canonicalPathFor(url.split('?')[0].split('#')[0]);
  return slug
    ? { yol, dil, detay: detayVerisi(KAYNAK_VERISI, slug, dil) }
    : { yol, dil, liste: listeVerisi(KAYNAK_VERISI, dil) };
}

/**
 * Kaynaklar liste ve ayrıntı sayfalarının <head>'i.
 *
 * Liste: CollectionPage + ItemList; ayrıntı: TechArticle + BreadcrumbList.
 * Sayfa verisi `<script id="kaynak-verisi">` olarak da basılıyor: istemci
 * ilk çizimi ağ beklemeden bu veriyle yapıyor (src/lib/kaynaklar.ts).
 */
function kaynakHead(gomulu, panelSettings) {
  const { dil } = gomulu;
  const seo = KAYNAKLAR_SEO[dil] ?? KAYNAKLAR_SEO[DEFAULT_LANGUAGE];
  const htmlLang = getLanguage(dil).htmlLang;
  const veriBetigi = {
    type: 'script',
    props: { type: 'application/json', id: 'kaynak-verisi', children: guvenliJson(gomulu) },
  };
  const ldBetigi = (data) => ({
    type: 'script',
    props: { type: 'application/ld+json', children: guvenliJson({ '@context': 'https://schema.org', ...data }) },
  });
  const anaSayfa = { '@type': 'ListItem', position: 1, name: seo.anaSayfa, item: absoluteUrl(localizedPath(dil, 'home')) };
  const listeOgesi = { '@type': 'ListItem', position: 2, name: seo.kaynaklar, item: absoluteUrl(kaynakYolu(dil)) };

  if (!('detay' in gomulu)) {
    const liste = gomulu.liste;
    const title = resolvePanelValue(panelSettings, PAGE_SEO_KEYS.kaynaklar.title, dil, seo.title);
    const description = resolvePanelValue(panelSettings, PAGE_SEO_KEYS.kaynaklar.description, dil, seo.description);
    return buildHead({
      title,
      description,
      canonicalPath: kaynakYolu(dil),
      ogType: 'website',
      lang: dil,
      extra: [
        ...hreflangElements('kaynaklar'),
        ldBetigi({
          '@type': 'CollectionPage',
          name: title,
          description,
          url: absoluteUrl(kaynakYolu(dil)),
          inLanguage: htmlLang,
          isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: `${SITE_URL}/` },
          publisher: YAYINCI,
          mainEntity: {
            '@type': 'ItemList',
            numberOfItems: liste.kaynaklar.length,
            itemListElement: liste.kaynaklar.map((k, i) => ({
              '@type': 'ListItem',
              position: i + 1,
              url: absoluteUrl(kaynakYolu(dil, k.slug)),
              name: k.baslik,
            })),
          },
        }),
        ldBetigi({ '@type': 'BreadcrumbList', itemListElement: [anaSayfa, listeOgesi] }),
        veriBetigi,
      ],
    });
  }

  const k = gomulu.detay?.kaynak;
  if (!k) {
    return buildHead({
      title: seo.title,
      description: seo.description,
      canonicalPath: kaynakYolu(dil),
      ogType: 'website',
      lang: dil,
      noindex: true,
      extra: [veriBetigi],
    });
  }
  const adres = absoluteUrl(kaynakYolu(dil, k.slug));
  const hreflang = [
    ...KAYNAK_DILLERI.map((d) => ({
      type: 'link',
      props: { rel: 'alternate', hreflang: getLanguage(d).htmlLang, href: absoluteUrl(kaynakYolu(d, k.slug)) },
    })),
    {
      type: 'link',
      props: { rel: 'alternate', hreflang: 'x-default', href: absoluteUrl(kaynakYolu(DEFAULT_LANGUAGE, k.slug)) },
    },
  ];
  return buildHead({
    title: kaynakBasligi(k.baslik, dil),
    description: metaAciklama(k.ozet),
    canonicalPath: kaynakYolu(dil, k.slug),
    ogType: 'article',
    lang: dil,
    extra: [
      ...hreflang,
      ldBetigi({
        '@type': 'TechArticle',
        headline: k.baslik,
        description: k.ozet,
        url: adres,
        mainEntityOfPage: { '@type': 'WebPage', '@id': adres },
        inLanguage: htmlLang,
        articleSection: k.kategori_adi,
        ...(k.etiketler.length ? { keywords: k.etiketler.join(', ') } : {}),
        ...(k.dogrulama_tarihi ? { dateModified: k.dogrulama_tarihi } : {}),
        about: { '@type': 'Thing', name: k.baslik, url: k.baglanti },
        author: { '@type': 'Person', name: 'Mehmet KURU', url: `${SITE_URL}/` },
        publisher: YAYINCI,
      }),
      ldBetigi({
        '@type': 'BreadcrumbList',
        itemListElement: [anaSayfa, listeOgesi, { '@type': 'ListItem', position: 3, name: k.baslik, item: adres }],
      }),
      veriBetigi,
    ],
  });
}

/**
 * Modül vitrini (Faz 4V) — liste, modül ve sektör paketi sayfalarının <head>'i.
 *
 * Liste: CollectionPage + ItemList (modüller) + ItemList (sektör paketleri);
 * modül: Service (+ fiyat varsa Offer — pakete dahil modülde paketin başlangıç
 * aylık tutarı; ayrı satılan modülde fiyat yok, `offers` yok) + FAQPage +
 * BreadcrumbList; paket: Service + paketteki modüller (OfferCatalog, fiyatsız).
 * Metinler ek paketten (`modulVitrini`, `modul`) o sayfanın dilinde. Fiyat
 * sayfaya da gömülüyor (`#modul-vitrini-verisi`): istemci ilk çizimi aynı
 * tutarla yapıyor (src/lib/modulVitrini.ts).
 */
function modulHead({ dil, tur, slug }, panelSettings) {
  const t = i18n.getFixedT(dil);
  const htmlLang = getLanguage(dil).htmlLang;
  const veriBetigi = {
    type: 'script',
    props: { type: 'application/json', id: 'modul-vitrini-verisi', children: guvenliJson({ fiyatlar: VITRIN_FIYATLARI }) },
  };
  const ldBetigi = (data) => ({
    type: 'script',
    props: { type: 'application/ld+json', children: guvenliJson({ '@context': 'https://schema.org', ...data }) },
  });
  const hreflang = (yolu) => [
    ...MODUL_DILLERI.map((d) => ({
      type: 'link',
      props: { rel: 'alternate', hreflang: getLanguage(d).htmlLang, href: absoluteUrl(yolu(d)) },
    })),
    { type: 'link', props: { rel: 'alternate', hreflang: 'x-default', href: absoluteUrl(yolu(DEFAULT_LANGUAGE)) } },
  ];
  const anaSayfa = { '@type': 'ListItem', position: 1, name: t('modulVitrini.seo.anaSayfa'), item: absoluteUrl(localizedPath(dil, 'home')) };
  const listeOgesi = { '@type': 'ListItem', position: 2, name: t('modulVitrini.seo.moduller'), item: absoluteUrl(modullerYolu(dil)) };
  const saglayici = { '@type': 'ProfessionalService', name: SITE_NAME, url: `${SITE_URL}/`, image: SITE_OG_IMAGE };
  const modulAdi = (anahtar) => t(`modul.m.${anahtar}.ad`);

  if (tur === 'liste') {
    const title = resolvePanelValue(panelSettings, PAGE_SEO_KEYS.moduller.title, dil, t('modulVitrini.seo.baslik'));
    const description = resolvePanelValue(panelSettings, PAGE_SEO_KEYS.moduller.description, dil, t('modulVitrini.seo.aciklama'));
    return buildHead({
      title,
      description,
      canonicalPath: modullerYolu(dil),
      ogType: 'website',
      lang: dil,
      extra: [
        ...hreflang((d) => modullerYolu(d)),
        ldBetigi({
          '@type': 'CollectionPage',
          name: title,
          description,
          url: absoluteUrl(modullerYolu(dil)),
          inLanguage: htmlLang,
          isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: `${SITE_URL}/` },
          publisher: YAYINCI,
          mainEntity: {
            '@type': 'ItemList',
            name: t('modulVitrini.seo.moduller'),
            numberOfItems: VITRIN_YAPISI.moduller.length,
            itemListElement: VITRIN_YAPISI.moduller.map((m, i) => ({
              '@type': 'ListItem',
              position: i + 1,
              url: absoluteUrl(modulYolu(dil, m.slug)),
              name: modulAdi(m.anahtar),
            })),
          },
          hasPart: {
            '@type': 'ItemList',
            name: t('modulVitrini.liste.paketlerBaslik'),
            numberOfItems: VITRIN_YAPISI.paketler.length,
            itemListElement: VITRIN_YAPISI.paketler.map((p, i) => ({
              '@type': 'ListItem',
              position: i + 1,
              url: absoluteUrl(paketYolu(dil, p.slug)),
              name: t(`modulVitrini.p.${p.anahtar}.ad`),
            })),
          },
        }),
        ldBetigi({ '@type': 'BreadcrumbList', itemListElement: [anaSayfa, listeOgesi] }),
        veriBetigi,
      ],
    });
  }

  const m = tur === 'modul' ? modulBul(VITRIN_YAPISI, slug) : null;
  const p = tur === 'paket' ? paketBul(VITRIN_YAPISI, slug) : null;
  if (!m && !p) {
    return buildHead({
      title: t('modulVitrini.seo.baslik'),
      description: t('modulVitrini.seo.aciklama'),
      canonicalPath: modullerYolu(dil),
      ogType: 'website',
      lang: dil,
      noindex: true,
      extra: [veriBetigi],
    });
  }

  if (m) {
    const ad = modulAdi(m.anahtar);
    const adres = absoluteUrl(modulYolu(dil, m.slug));
    const ozet = t(`modulVitrini.m.${m.anahtar}.ozet`);
    const fiyat = modulFiyati(m, VITRIN_FIYATLARI);
    const sss = t(`modulVitrini.m.${m.anahtar}.sss`, { returnObjects: true });
    const offers =
      fiyat && fiyat.tutar !== null
        ? {
            offers: {
              '@type': 'Offer',
              price: fiyat.tutar.toFixed(2),
              priceCurrency: fiyat.paraBirimi,
              priceSpecification: {
                '@type': 'UnitPriceSpecification',
                price: fiyat.tutar.toFixed(2),
                priceCurrency: fiyat.paraBirimi,
                unitCode: 'MON',
                referenceQuantity: { '@type': 'QuantitativeValue', value: 1, unitCode: 'MON' },
              },
              description: t('modulVitrini.fiyat.dahil', { paket: olcekAdi(VITRIN_FIYATLARI, fiyat.paket, dil) }),
              url: absoluteUrl(localizedPath(dil, 'services')),
              availability: 'https://schema.org/InStock',
            },
          }
        : {};
    return buildHead({
      title: `${ad} · ${t('modulVitrini.seo.detaySonEki')}`,
      description: metaAciklama(ozet),
      canonicalPath: modulYolu(dil, m.slug),
      ogType: 'website',
      lang: dil,
      extra: [
        ...hreflang((d) => modulYolu(d, m.slug)),
        ldBetigi({
          '@type': 'Service',
          name: ad,
          description: ozet,
          url: adres,
          serviceType: t(`modul.kategori.${m.kategori}`),
          category: t(`modul.kategori.${m.kategori}`),
          inLanguage: htmlLang,
          provider: saglayici,
          audience: { '@type': 'BusinessAudience', audienceType: t(`modulVitrini.m.${m.anahtar}.kimIcin`) },
          ...offers,
        }),
        ...(Array.isArray(sss) && sss.length
          ? [
              ldBetigi({
                '@type': 'FAQPage',
                mainEntity: sss.map((x) => ({ '@type': 'Question', name: x.s, acceptedAnswer: { '@type': 'Answer', text: x.c } })),
              }),
            ]
          : []),
        ldBetigi({
          '@type': 'BreadcrumbList',
          itemListElement: [anaSayfa, listeOgesi, { '@type': 'ListItem', position: 3, name: ad, item: adres }],
        }),
        veriBetigi,
      ],
    });
  }

  const ad = t(`modulVitrini.p.${p.anahtar}.ad`);
  const adres = absoluteUrl(paketYolu(dil, p.slug));
  const ozet = t(`modulVitrini.p.${p.anahtar}.ozet`);
  return buildHead({
    title: `${ad} · ${t('modulVitrini.seo.paketSonEki')}`,
    description: metaAciklama(ozet),
    canonicalPath: paketYolu(dil, p.slug),
    ogType: 'website',
    lang: dil,
    extra: [
      ...hreflang((d) => paketYolu(d, p.slug)),
      ldBetigi({
        '@type': 'Service',
        name: ad,
        description: ozet,
        url: adres,
        serviceType: t('modulVitrini.detay.sektorPaketi'),
        inLanguage: htmlLang,
        provider: saglayici,
        audience: { '@type': 'BusinessAudience', audienceType: t(`modulVitrini.p.${p.anahtar}.kimIcin`) },
        hasOfferCatalog: {
          '@type': 'OfferCatalog',
          name: t('modulVitrini.detay.paketModulleri'),
          itemListElement: p.moduller
            .map((k) => VITRIN_YAPISI.moduller.find((x) => x.anahtar === k))
            .filter(Boolean)
            .map((x) => ({ '@type': 'Service', name: modulAdi(x.anahtar), url: absoluteUrl(modulYolu(dil, x.slug)) })),
        },
      }),
      ldBetigi({
        '@type': 'BreadcrumbList',
        itemListElement: [anaSayfa, listeOgesi, { '@type': 'ListItem', position: 3, name: ad, item: adres }],
      }),
      veriBetigi,
    ],
  });
}

/**
 * Ücretsiz SEO araçları (Faz 4S) — dizin ve araç sayfalarının <head>'i.
 *
 * Dizin: CollectionPage + ItemList (araçlar) + BreadcrumbList + FAQPage (sayfada görünen SSS).
 * Araç: WebApplication (ücretsiz: Offer price 0) + BreadcrumbList + FAQPage (sayfada görünen SSS).
 * Metinler ek paketten (`seoAraclari`) o sayfanın dilinde; panelde dizin için SEO metni
 * girilmişse o kazanır (PAGE_SEO_KEYS.seoAraclari).
 */
function seoAracHead({ dil, slug }, panelSettings) {
  const t = i18n.getFixedT(dil);
  const htmlLang = getLanguage(dil).htmlLang;
  const ldBetigi = (data) => ({
    type: 'script',
    props: { type: 'application/ld+json', children: guvenliJson({ '@context': 'https://schema.org', ...data }) },
  });
  const hreflang = (yolu) => [
    ...SEO_ARAC_DILLERI.map((d) => ({
      type: 'link',
      props: { rel: 'alternate', hreflang: getLanguage(d).htmlLang, href: absoluteUrl(yolu(d)) },
    })),
    { type: 'link', props: { rel: 'alternate', hreflang: 'x-default', href: absoluteUrl(yolu(DEFAULT_LANGUAGE)) } },
  ];
  const sssLd = (sorular) =>
    Array.isArray(sorular) && sorular.length
      ? [ldBetigi({ '@type': 'FAQPage', mainEntity: sorular.map((x) => ({ '@type': 'Question', name: x.s, acceptedAnswer: { '@type': 'Answer', text: x.c } })) })]
      : [];
  const anaSayfa = { '@type': 'ListItem', position: 1, name: t('seoAraclari.seo.anaSayfa'), item: absoluteUrl(localizedPath(dil, 'home')) };
  const dizinOgesi = { '@type': 'ListItem', position: 2, name: t('seoAraclari.seo.araclar'), item: absoluteUrl(seoAraclariYolu(dil)) };

  if (!slug) {
    const title = resolvePanelValue(panelSettings, PAGE_SEO_KEYS.seoAraclari.title, dil, t('seoAraclari.seo.baslik'));
    const description = resolvePanelValue(panelSettings, PAGE_SEO_KEYS.seoAraclari.description, dil, t('seoAraclari.seo.aciklama'));
    return buildHead({
      title,
      description,
      canonicalPath: seoAraclariYolu(dil),
      ogType: 'website',
      lang: dil,
      extra: [
        ...hreflang((d) => seoAraclariYolu(d)),
        ldBetigi({
          '@type': 'CollectionPage',
          name: title,
          description,
          url: absoluteUrl(seoAraclariYolu(dil)),
          inLanguage: htmlLang,
          isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: `${SITE_URL}/` },
          publisher: YAYINCI,
          mainEntity: {
            '@type': 'ItemList',
            numberOfItems: SEO_ARACLARI.length,
            itemListElement: SEO_ARACLARI.map((a, i) => ({
              '@type': 'ListItem',
              position: i + 1,
              url: absoluteUrl(seoAracYolu(dil, a.slug)),
              name: t(`seoAraclari.arac.${a.anahtar}.ad`),
            })),
          },
        }),
        ldBetigi({ '@type': 'BreadcrumbList', itemListElement: [anaSayfa, dizinOgesi] }),
        ...sssLd(t('seoAraclari.dizin.sss', { returnObjects: true })),
      ],
    });
  }

  const a = seoAracBul(slug);
  if (!a) {
    return buildHead({
      title: t('seoAraclari.seo.baslik'),
      description: t('seoAraclari.seo.aciklama'),
      canonicalPath: seoAraclariYolu(dil),
      ogType: 'website',
      lang: dil,
      noindex: true,
    });
  }
  const k = `seoAraclari.arac.${a.anahtar}`;
  const ad = t(`${k}.ad`);
  const adres = absoluteUrl(seoAracYolu(dil, a.slug));
  const aciklama = t(`${k}.seoAciklama`);
  return buildHead({
    title: `${t(`${k}.seoBaslik`)} | Mehmet KURU`,
    description: aciklama,
    canonicalPath: seoAracYolu(dil, a.slug),
    ogType: 'website',
    lang: dil,
    extra: [
      ...hreflang((d) => seoAracYolu(d, a.slug)),
      ldBetigi({
        '@type': 'WebApplication',
        name: ad,
        description: aciklama,
        url: adres,
        applicationCategory: 'DeveloperApplication',
        applicationSubCategory: 'SEO',
        operatingSystem: 'Any',
        browserRequirements: 'Requires JavaScript',
        isAccessibleForFree: true,
        inLanguage: htmlLang,
        featureList: t(`${k}.neler`, { returnObjects: true }),
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
        provider: { '@type': 'ProfessionalService', name: SITE_NAME, url: `${SITE_URL}/`, image: SITE_OG_IMAGE },
        isPartOf: { '@type': 'CollectionPage', name: t('seoAraclari.seo.araclar'), url: absoluteUrl(seoAraclariYolu(dil)) },
      }),
      ldBetigi({
        '@type': 'BreadcrumbList',
        itemListElement: [anaSayfa, dizinOgesi, { '@type': 'ListItem', position: 3, name: ad, item: adres }],
      }),
      ...sssLd(t(`${k}.sss`, { returnObjects: true })),
    ],
  });
}

/**
 * hreflang bağlantıları.
 *
 * Yalnızca gerçekten var olan çeviriler için üretiliyor. Önceki hâlinde
 * Layout her sayfaya yedi dil için `?lang=xx` alternatifi basıyordu; o
 * adreslerin hepsi aynı HTML'i döndürdüğü için Google'a 63 sayfanın yedi
 * kopyası bildiriliyordu. Blog Türkçe olduğundan blog sayfalarına yalnızca
 * kendine gönderen tek bir tr alternatifi konuyor.
 */
function hreflangElements(pageKey) {
  if (!pageKey) return [];

  const links = [];
  for (const code of Object.keys(PAGE_SEO)) {
    links.push({
      type: 'link',
      props: {
        rel: 'alternate',
        hreflang: getLanguage(code).htmlLang,
        href: absoluteUrl(localizedPath(code, pageKey)),
      },
    });
  }
  links.push({
    type: 'link',
    props: {
      rel: 'alternate',
      hreflang: 'x-default',
      href: absoluteUrl(localizedPath(DEFAULT_LANGUAGE, pageKey)),
    },
  });
  return links;
}

function buildHead({
  title,
  description,
  canonicalPath,
  ogType,
  lang,
  image,
  extra = [],
  noindex = false,
}) {
  const canonical = absoluteUrl(canonicalPath);
  const ogImage = image || SITE_OG_IMAGE;
  const language = getLanguage(lang);

  const elements = [
    { type: 'link', props: { rel: 'canonical', href: canonical } },
    noindex ? { type: 'meta', props: { name: 'robots', content: 'noindex, follow' } } : null,
    meta('name', 'description', description),
    meta('property', 'og:title', title),
    meta('property', 'og:description', description),
    meta('property', 'og:url', canonical),
    meta('property', 'og:type', ogType),
    meta('property', 'og:site_name', SITE_NAME),
    meta('property', 'og:locale', language.locale),
    meta('property', 'og:image', ogImage),
    meta('name', 'twitter:card', 'summary_large_image'),
    meta('name', 'twitter:title', title),
    meta('name', 'twitter:description', description),
    meta('name', 'twitter:image', ogImage),
    ...extra,
  ].filter(Boolean);

  return { title, lang: language.htmlLang, elements: new Set(elements) };
}

function getHead(url, panelSettings = {}, kaynakVerisi = null, yasalVerisi = null, modulEslesmesi = null) {
  // Kaynaklar (liste + ayrıntı, 7 dil) — PAGE_SEO yerine kendi metinleri.
  if (kaynakVerisi) return kaynakHead(kaynakVerisi, panelSettings);
  // Modül vitrini (Faz 4V) — metinleri ek pakette; PAGE_SEO'da yok.
  if (modulEslesmesi) return modulHead(modulEslesmesi, panelSettings);
  // Ücretsiz SEO araçları (Faz 4S) — metinleri ek pakette; PAGE_SEO'da yok.
  const seoArac = seoAracYolunuCoz(url);
  if (seoArac) return seoAracHead(seoArac, panelSettings);

  const slug = getBlogSlug(url);

  // Tekil blog yazısı — meta verisi markdown frontmatter'ından geliyor.
  if (slug) {
    const post = getBlogPost(slug);
    if (!post) {
      return buildHead({
        title: `Sayfa bulunamadı | ${SITE_NAME}`,
        description: 'Aradığınız yazı bulunamadı.',
        canonicalPath: '/blog',
        ogType: 'website',
        lang: DEFAULT_LANGUAGE,
        noindex: true,
      });
    }

    const seo = getPostSeoMeta(post);
    const postUrl = absoluteUrl(`/blog/${post.slug}`);
    const faq = extractFaq(post.markdown);

    /*
     * Yapısal veri.
     *
     * Daha önce her sayfa ana sayfanın `ProfessionalService` bloğunu
     * taşıyordu: 61 makale kendini "profesyonel hizmet" sayfası ilan
     * ediyordu. Artık yazılar kendi türlerini bildiriyor. FAQ bölümü olan
     * 57 yazıda `FAQPage` da üretiliyor — metin zaten sayfada, işaretleme
     * yoktu.
     */
    const structured = [
      jsonLd({
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        headline: post.title,
        description: post.description,
        url: postUrl,
        mainEntityOfPage: { '@type': 'WebPage', '@id': postUrl },
        inLanguage: DEFAULT_LANGUAGE,
        ...(seo.publishedTime ? { datePublished: seo.publishedTime } : {}),
        ...(seo.ogImage ? { image: seo.ogImage } : {}),
        ...(post.frontmatter.tags?.length ? { keywords: post.frontmatter.tags.join(', ') } : {}),
        ...(post.category ? { articleSection: post.category } : {}),
        author: { '@type': 'Person', name: 'Mehmet KURU', url: `${SITE_URL}/` },
        publisher: {
          '@type': 'Organization',
          name: SITE_NAME,
          url: `${SITE_URL}/`,
          logo: { '@type': 'ImageObject', url: SITE_OG_IMAGE },
        },
      }),
      jsonLd({
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        itemListElement: [
          { '@type': 'ListItem', position: 1, name: 'Ana Sayfa', item: `${SITE_URL}/` },
          { '@type': 'ListItem', position: 2, name: 'Blog', item: absoluteUrl('/blog') },
          { '@type': 'ListItem', position: 3, name: post.title, item: postUrl },
        ],
      }),
      ...(faq.length > 0
        ? [
            jsonLd({
              '@context': 'https://schema.org',
              '@type': 'FAQPage',
              mainEntity: faq.map((entry) => ({
                '@type': 'Question',
                name: entry.question,
                acceptedAnswer: { '@type': 'Answer', text: entry.answer },
              })),
            }),
          ]
        : []),
    ];

    return buildHead({
      title: seo.title,
      description: seo.description,
      canonicalPath: `/blog/${post.slug}`,
      ogType: 'article',
      lang: DEFAULT_LANGUAGE,
      image: seo.ogImage,
      extra: [
        meta('name', 'keywords', seo.keywords),
        meta('property', 'article:published_time', seo.publishedTime),
        ...(seo.tags ?? []).map((tag) => meta('property', 'article:tag', tag)),
        ...structured,
      ].filter(Boolean),
    });
  }

  const { lang, pageKey, path } = resolveRoute(url);

  // Blog dizini — yalnızca Türkçe.
  if (path === BLOG_INDEX_ROUTE.routePath) {
    return buildHead({
      title: resolvePanelValue(
        panelSettings, PAGE_SEO_KEYS.blog.title, DEFAULT_LANGUAGE, BLOG_INDEX_ROUTE.title,
      ),
      description: resolvePanelValue(
        panelSettings, PAGE_SEO_KEYS.blog.description, DEFAULT_LANGUAGE, BLOG_INDEX_ROUTE.description,
      ),
      canonicalPath: BLOG_INDEX_ROUTE.routePath,
      ogType: 'website',
      lang: DEFAULT_LANGUAGE,
      extra: [
        jsonLd({
          '@context': 'https://schema.org',
          '@type': 'Blog',
          name: BLOG_INDEX_ROUTE.title,
          description: BLOG_INDEX_ROUTE.description,
          url: absoluteUrl(BLOG_INDEX_ROUTE.routePath),
          inLanguage: DEFAULT_LANGUAGE,
          publisher: { '@type': 'Organization', name: SITE_NAME, url: `${SITE_URL}/` },
        }),
        jsonLd({
          '@context': 'https://schema.org',
          '@type': 'BreadcrumbList',
          itemListElement: [
            { '@type': 'ListItem', position: 1, name: 'Ana Sayfa', item: `${SITE_URL}/` },
            { '@type': 'ListItem', position: 2, name: 'Blog', item: absoluteUrl('/blog') },
          ],
        }),
      ],
    });
  }

  // Yasal sayfalar (Faz 3Y): varsayılan metin yasal-seo.js'te (ana pakete girmesin diye),
  // panelden girilen SEO metni yine kazanır. Veri sorumlusu bilgileri sayfaya gömülüyor:
  // istemci ilk çizimi prerender'la aynı değerlerle yapıyor (src/lib/yasal.ts).
  if (pageKey && YASAL_SAYFALAR.includes(pageKey)) {
    const seo = yasalSeo(lang, pageKey);
    const keys = PAGE_SEO_KEYS[pageKey];
    return buildHead({
      title: resolvePanelValue(panelSettings, keys.title, lang, seo.title),
      description: resolvePanelValue(panelSettings, keys.description, lang, seo.description),
      canonicalPath: localizedPath(lang, pageKey),
      ogType: 'website',
      lang,
      extra: [
        ...hreflangElements(pageKey),
        {
          type: 'script',
          props: { type: 'application/json', id: 'yasal-verisi', children: guvenliJson(yasalVerisi ?? {}) },
        },
      ],
    });
  }

  // Faz 5K — ortaklık programı: başlık/açıklama ek pakette (ana pakete girmesin), panel değeri yine kazanır.
  if (pageKey === 'ortaklik') {
    const t = i18n.getFixedT(lang);
    const keys = PAGE_SEO_KEYS.ortaklik;
    const title = resolvePanelValue(panelSettings, keys.title, lang, t('ortaklik.seo.baslik'));
    const description = resolvePanelValue(panelSettings, keys.description, lang, t('ortaklik.seo.aciklama'));
    return buildHead({
      title,
      description,
      canonicalPath: localizedPath(lang, pageKey),
      ogType: 'website',
      lang,
      extra: [
        ...hreflangElements(pageKey),
        jsonLd({
          '@context': 'https://schema.org',
          '@type': 'WebPage',
          name: title,
          description,
          url: absoluteUrl(localizedPath(lang, pageKey)),
          inLanguage: getLanguage(lang).htmlLang,
          isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: `${SITE_URL}/` },
        }),
      ],
    });
  }

  // Çok dilli statik sayfalar.
  if (pageKey) {
    const seo = PAGE_SEO[lang][pageKey];
    const keys = PAGE_SEO_KEYS[pageKey];
    return buildHead({
      // Panelde o dil için girilmiş bir değer varsa o kazanır; yoksa koddaki
      // varsayılan kullanılır. İkisi de aynı yerden okunduğu için Google'ın
      // gördüğü metinle ziyaretçinin gördüğü metin ayrışmıyor.
      title: resolvePanelValue(panelSettings, keys.title, lang, seo.title),
      description: resolvePanelValue(panelSettings, keys.description, lang, seo.description),
      canonicalPath: localizedPath(lang, pageKey),
      ogType: 'website',
      lang,
      extra: [
        ...hreflangElements(pageKey),
        // Yapısal veri yalnızca Türkçe ana sayfada; aksi hâlde her sayfa
        // kendini ayrı bir "profesyonel hizmet" kaydı olarak bildiriyordu.
        ...(pageKey === 'home' && lang === DEFAULT_LANGUAGE ? [jsonLd(ORGANIZATION_JSONLD)] : []),
        ...(pageKey === 'home' && lang === DEFAULT_LANGUAGE && faqJsonLd()
          ? [jsonLd(faqJsonLd())]
          : []),
      ],
    });
  }

  return buildHead({
    title: SITE_NAME,
    description: PAGE_SEO[DEFAULT_LANGUAGE].home.description,
    canonicalPath: path,
    ogType: 'website',
    lang: DEFAULT_LANGUAGE,
    noindex: true,
  });
}

export async function prerender({ url }) {
  const panelSettings = await loadPanelSettings();
  const { lang } = resolveRoute(url);
  const slug = getBlogSlug(url);
  const isBlog = canonicalPathFor(url).startsWith('/blog');

  // Kaynaklar: sayfa bu veriyle çiziliyor ve aynısı <head>'e gömülüyor.
  // Diğer sayfalarda null — bir önceki sayfanın verisi sızmasın.
  const kaynakEslesmesi = kaynakYolunuCoz(url);
  const kaynakVerisi = kaynakEslesmesi ? kaynakGomuluVerisi(url, kaynakEslesmesi) : null;
  gomuluVeriyiAyarla(kaynakVerisi);

  // Yasal sayfalar: veri sorumlusu bilgileri canlı API'den (5 sn; olmazsa varsayılanlar).
  const yasalMi = YASAL_SAYFALAR.includes(resolveRoute(url).pageKey ?? '');
  const yasalVerisi = yasalMi ? await yasalAyarlariniYukle() : null;
  yasalVeriyiAyarla(yasalVerisi);

  // Modül vitrini: fiyatlar sayfaya gömülüyor (diğer sayfalarda null — sızmasın).
  const modulEslesmesi = modulYolunuCoz(url);
  gomuluFiyatlariAyarla(modulEslesmesi ? VITRIN_FIYATLARI : null);

  // Blog Türkçe; statik sayfalar kendi dilinde render edilir.
  await i18n.changeLanguage(isBlog ? DEFAULT_LANGUAGE : lang);

  const html = renderApp(url);
  const modulYok =
    Boolean(modulEslesmesi) &&
    ((modulEslesmesi.tur === 'modul' && !modulBul(VITRIN_YAPISI, modulEslesmesi.slug)) ||
      (modulEslesmesi.tur === 'paket' && !paketBul(VITRIN_YAPISI, modulEslesmesi.slug)));
  const seoArac = seoAracYolunuCoz(url);
  const is404 =
    (Boolean(slug) && !getBlogPost(slug)) ||
    Boolean(kaynakVerisi && 'detay' in kaynakVerisi && !kaynakVerisi.detay) ||
    modulYok ||
    Boolean(seoArac?.slug && !seoAracBul(seoArac.slug));

  return {
    html,
    head: getHead(url, panelSettings, kaynakVerisi, yasalVerisi, modulEslesmesi),
    ...(is404 ? { statusCode: 404 } : {}),
  };
}
