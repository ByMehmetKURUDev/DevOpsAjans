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

import Layout from '../src/components/Layout';
import LanguageGate from '../src/components/LanguageGate';
import Index from '../src/pages/Index';
import Services from '../src/pages/Services';
import Portfolio from '../src/pages/Portfolio';
import Contact from '../src/pages/Contact';
import BlogIndexPage from '../src/pages/blog/BlogIndexPage';
import BlogPostPage from '../src/pages/blog/BlogPostPage';
import { extractFaq, getBlogPost, getPostSeoMeta } from '../src/lib/blog';
import { loadPanelSettings, resolvePanelValue } from './settings.js';
import {
  BLOG_INDEX_ROUTE,
  DEFAULT_LANGUAGE,
  ORGANIZATION_JSONLD,
  PAGE_SEO,
  PAGE_SEO_KEYS,
  SITE_NAME,
  SITE_OG_IMAGE,
  SITE_URL,
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
            h(Route, { path: '/contact', element: h(Contact, null) }),
            h(Route, { path: '/blog', element: h(BlogIndexPage, null) }),
            h(Route, { path: '/blog/:slug', element: h(BlogPostPage, null) }),
          ),
          h(
            Route,
            { path: '/:lang', element: h(LanguageGate, null) },
            h(Route, { index: true, element: h(Index, null) }),
            h(Route, { path: 'services', element: h(Services, null) }),
            h(Route, { path: 'portfolio', element: h(Portfolio, null) }),
            h(Route, { path: 'contact', element: h(Contact, null) }),
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

function jsonLd(data) {
  return {
    type: 'script',
    props: { type: 'application/ld+json', children: JSON.stringify(data) },
  };
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

function getHead(url, panelSettings = {}) {
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

  // Blog Türkçe; statik sayfalar kendi dilinde render edilir.
  await i18n.changeLanguage(isBlog ? DEFAULT_LANGUAGE : lang);

  const html = renderApp(url);
  const is404 = Boolean(slug) && !getBlogPost(slug);

  return {
    html,
    head: getHead(url, panelSettings),
    ...(is404 ? { statusCode: 404 } : {}),
  };
}
