import path from 'node:path';
import { seoContentDir, normalizeRouteFromMarkdown, collectMarkdownFiles } from './utils.js';
import { BLOG_INDEX_ROUTE, getLocalizedRoutes } from './site.js';

export function getBlogRoutes() {
  const routes = new Set([`${BLOG_INDEX_ROUTE.routePath}/`]);

  for (const filePath of collectMarkdownFiles(seoContentDir)) {
    const relativePath = path.relative(seoContentDir, filePath);
    routes.add(normalizeRouteFromMarkdown(relativePath));
  }

  return Array.from(routes).sort();
}

/**
 * Prerender edilecek bütün yollar: yedi dildeki statik sayfalar + Türkçe blog.
 *
 * Sondaki eğik çizgi, çıktının `dist/<yol>/index.html` olarak yazılmasını
 * sağlıyor; canonical adresler eğik çizgisiz biçimi kullanır.
 *
 * Ana sayfa da bu listede: daha önce prerender yalnızca `/blog/**` ile
 * besleniyordu ve `dist/index.html` gövdesi bomboş çıkıyordu.
 */
export function getAllPrerenderRoutes() {
  const localized = getLocalizedRoutes().map((route) =>
    route.path === '/' ? '/' : `${route.path}/`,
  );

  return Array.from(new Set([...localized, ...getBlogRoutes()])).sort();
}
