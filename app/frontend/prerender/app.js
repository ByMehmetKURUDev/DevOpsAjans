import React from 'react';
import { renderToString } from 'react-dom/server';
import { Route, Routes } from 'react-router-dom';
import { StaticRouter } from 'react-router-dom/server';
import { I18nextProvider } from 'react-i18next';

import i18n from '../src/i18n';
import Layout from '../src/components/Layout';
import Index from '../src/pages/Index';
import Services from '../src/pages/Services';
import Portfolio from '../src/pages/Portfolio';
import Contact from '../src/pages/Contact';
import BlogIndexPage from '../src/pages/blog/BlogIndexPage';
import BlogPostPage from '../src/pages/blog/BlogPostPage';
import { getBlogPost, getPostSeoMeta } from '../src/lib/blog';
import {
  BLOG_INDEX_ROUTE,
  ORGANIZATION_JSONLD,
  SITE_LANG,
  SITE_LOCALE,
  SITE_NAME,
  SITE_OG_IMAGE,
  STATIC_ROUTES,
  absoluteUrl,
} from './site.js';

const h = React.createElement;

/**
 * Statik sayfalar burada lazy() olmadan kuruluyor: renderToString Suspense'i
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
        ),
      ),
    ),
  );
}

/** URL'i sondaki eğik çizgiden bağımsız normalize eder. */
function normalizePath(url) {
  const path = url.split('?')[0].split('#')[0];
  const trimmed = path.replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
}

function getBlogSlug(url) {
  const path = normalizePath(url);
  if (!path.startsWith('/blog')) return null;
  const slug = path.slice('/blog'.length).replace(/^\/+/, '');
  return slug || null;
}

function meta(attribute, key, value) {
  if (!value) return null;
  return { type: 'meta', props: { [attribute]: key, content: value } };
}

/**
 * Her sayfa için eksiksiz bir `<head>` üretir.
 *
 * Bu etiketlerin hiçbiri artık `index.html` içinde durmuyor: prerender
 * eklentisi head'e ekleme yapıyor, var olanı değiştirmiyor. Sabit etiketler
 * orada kalsaydı her sayfada ana sayfanın canonical'ı ve og etiketleri
 * ikinci bir kopya olarak kalırdı — canlıdaki hatanın kaynağı buydu.
 */
function buildHead({ title, description, canonicalPath, ogType, image, extra = [], noindex = false }) {
  const canonical = absoluteUrl(canonicalPath);
  const ogImage = image || SITE_OG_IMAGE;

  const elements = [
    { type: 'link', props: { rel: 'canonical', href: canonical } },
    noindex ? { type: 'meta', props: { name: 'robots', content: 'noindex, follow' } } : null,
    meta('name', 'description', description),
    meta('property', 'og:title', title),
    meta('property', 'og:description', description),
    meta('property', 'og:url', canonical),
    meta('property', 'og:type', ogType),
    meta('property', 'og:site_name', SITE_NAME),
    meta('property', 'og:locale', SITE_LOCALE),
    meta('property', 'og:image', ogImage),
    meta('name', 'twitter:card', 'summary_large_image'),
    meta('name', 'twitter:title', title),
    meta('name', 'twitter:description', description),
    meta('name', 'twitter:image', ogImage),
    ...extra,
  ].filter(Boolean);

  return { title, lang: SITE_LANG, elements: new Set(elements) };
}

function jsonLd(data) {
  return {
    type: 'script',
    props: { type: 'application/ld+json', children: JSON.stringify(data) },
  };
}

function getHead(url) {
  const path = normalizePath(url);
  const slug = getBlogSlug(url);

  // Tekil blog yazısı — meta verisi markdown frontmatter'ından geliyor.
  if (slug) {
    const post = getBlogPost(slug);
    if (!post) {
      return buildHead({
        title: `Sayfa bulunamadı | ${SITE_NAME}`,
        description: 'Aradığınız yazı bulunamadı.',
        canonicalPath: '/blog/',
        ogType: 'website',
        noindex: true,
      });
    }

    const seo = getPostSeoMeta(post);
    const extra = [
      meta('name', 'keywords', seo.keywords),
      meta('property', 'article:published_time', seo.publishedTime),
      ...(seo.tags ?? []).map((tag) => meta('property', 'article:tag', tag)),
    ].filter(Boolean);

    return buildHead({
      title: seo.title,
      description: seo.description,
      canonicalPath: `/blog/${post.slug}/`,
      ogType: 'article',
      image: seo.ogImage,
      extra,
    });
  }

  // Blog dizini.
  if (path === '/blog') {
    return buildHead({
      title: BLOG_INDEX_ROUTE.title,
      description: BLOG_INDEX_ROUTE.description,
      canonicalPath: BLOG_INDEX_ROUTE.path,
      ogType: 'website',
    });
  }

  // Statik sayfalar.
  const route = STATIC_ROUTES.find((entry) => entry.routePath === path);
  if (route) {
    return buildHead({
      title: route.title,
      description: route.description,
      canonicalPath: route.path,
      ogType: 'website',
      // Yapısal veri yalnızca ana sayfada; aksi hâlde her yazı kendini
      // "profesyonel hizmet" sayfası ilan ediyordu.
      extra: route.routePath === '/' ? [jsonLd(ORGANIZATION_JSONLD)] : [],
    });
  }

  return buildHead({
    title: `${SITE_NAME}`,
    description: STATIC_ROUTES[0].description,
    canonicalPath: path === '/' ? '/' : `${path}/`,
    ogType: 'website',
    noindex: true,
  });
}

export async function prerender({ url }) {
  const html = renderApp(url);
  const slug = getBlogSlug(url);
  const is404 = Boolean(slug) && !getBlogPost(slug);

  return {
    html,
    head: getHead(url),
    ...(is404 ? { statusCode: 404 } : {}),
  };
}
