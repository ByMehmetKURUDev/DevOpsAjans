import fs from 'node:fs';
import path from 'node:path';
import { parse as parseYaml } from 'yaml';
import { seoContentDir, normalizeRouteFromMarkdown, collectMarkdownFiles } from './utils.js';

const VIRTUAL_ID = 'virtual:blog-index';
const RESOLVED_ID = '\0virtual:blog-index';

function parseFrontmatter(raw) {
  const match = raw.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!match) return { data: {}, body: raw };
  try {
    return { data: parseYaml(match[1]) ?? {}, body: raw.slice(match[0].length) };
  } catch {
    return { data: {}, body: raw };
  }
}

function firstWords(text, limit = 160) {
  return text
    .replace(/^#+\s+/gm, '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/[*_`>#-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, limit);
}

function titleFromSlug(slug) {
  return slug
    .split('-')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

/**
 * Blog meta verisini derleme sırasında üretir.
 *
 * `lib/blog.ts` bütün markdown dosyalarını `eager: true` ile içeri alıyordu:
 * 61 makalenin tam metni tek bir chunk'a giriyor ve blog listesini açan
 * herkes 500 kB'lık o paketi indiriyordu — liste sayfasının gövde metnine
 * hiç ihtiyacı yokken. Bu eklenti yalnızca frontmatter'dan üretilmiş hafif
 * bir indeks yayınlıyor; gövdeler ayrı kalıyor.
 */
export function blogIndexPlugin() {
  function buildIndex() {
    const entries = [];

    for (const filePath of collectMarkdownFiles(seoContentDir)) {
      const raw = fs.readFileSync(filePath, 'utf8');
      const { data, body } = parseFrontmatter(raw);
      const relative = path.relative(seoContentDir, filePath).replace(/\\/g, '/');
      const slug = normalizeRouteFromMarkdown(relative)
        .replace(/^\/blog\//, '')
        .replace(/\/$/, '');

      const tags = Array.isArray(data.tags) ? data.tags.map(String) : undefined;

      entries.push({
        slug,
        title: data.title ? String(data.title) : titleFromSlug(slug),
        description: data.description ? String(data.description) : firstWords(body),
        category: data.category ? String(data.category) : tags?.[0],
        date: data.date ? String(data.date) : undefined,
        tags,
      });
    }

    entries.sort((a, b) => {
      const at = a.date ? Date.parse(a.date) : NaN;
      const bt = b.date ? Date.parse(b.date) : NaN;
      if (!Number.isNaN(at) && !Number.isNaN(bt) && at !== bt) return bt - at;
      if (!Number.isNaN(at) && Number.isNaN(bt)) return -1;
      if (Number.isNaN(at) && !Number.isNaN(bt)) return 1;
      return a.slug.localeCompare(b.slug);
    });

    return entries;
  }

  return {
    name: 'blog-index',
    resolveId(id) {
      return id === VIRTUAL_ID ? RESOLVED_ID : null;
    },
    load(id) {
      if (id !== RESOLVED_ID) return null;
      return `export const blogIndex = ${JSON.stringify(buildIndex())};`;
    },
    configureServer(server) {
      // Geliştirme sırasında markdown değişince indeks tazelensin.
      server.watcher.add(seoContentDir);
      server.watcher.on('all', (_event, file) => {
        if (!file.endsWith('.md')) return;
        const mod = server.moduleGraph.getModuleById(RESOLVED_ID);
        if (mod) server.moduleGraph.invalidateModule(mod);
      });
    },
  };
}
