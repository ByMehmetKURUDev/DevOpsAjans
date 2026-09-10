import path from 'node:path';
import { seoContentDir, normalizeRouteFromMarkdown, collectMarkdownFiles } from './utils.js';
import { BLOG_INDEX_ROUTE, STATIC_ROUTES } from './site.js';

export function getBlogRoutes() {
  const routes = new Set([BLOG_INDEX_ROUTE.path]);

  for (const filePath of collectMarkdownFiles(seoContentDir)) {
    const relativePath = path.relative(seoContentDir, filePath);
    routes.add(normalizeRouteFromMarkdown(relativePath));
  }

  return Array.from(routes).sort();
}

/**
 * Prerender edilecek bütün yollar: statik sayfalar + blog.
 *
 * Ana sayfa da bu listede; daha önce prerender yalnızca `/blog/**` ile
 * besleniyordu ve `dist/index.html` gövdesi bomboş çıkıyordu.
 */
export function getAllPrerenderRoutes() {
  return Array.from(new Set([...STATIC_ROUTES.map((r) => r.path), ...getBlogRoutes()])).sort();
}
