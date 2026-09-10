import { blogIndex } from 'virtual:blog-index';

/** Blog listesi için hafif meta kayıt — gövde metni içermez. */
export interface BlogIndexEntry {
  slug: string;
  title: string;
  description: string;
  category?: string;
  date?: string;
  tags?: string[];
}

/**
 * Yayın tarihine göre sıralı yazı listesi.
 *
 * Derleme sırasında `prerender/blog-index-plugin.js` tarafından üretilir.
 * Liste sayfası ve ilgili yazılar bloğu yalnızca bunu kullanır; markdown
 * gövdeleri ayrı bir chunk'ta kalır ve sadece yazı sayfası indirir.
 */
export const blogIndexEntries = blogIndex as BlogIndexEntry[];

export const blogIndexCategories: string[] = Array.from(
  new Set(blogIndexEntries.map((e) => e.category).filter((c): c is string => Boolean(c))),
).sort((a, b) => a.localeCompare(b, 'tr'));

/** Aynı kategori ve ortak etiketlere göre ilgili yazılar. */
export function getRelatedEntries(slug: string, limit = 3): BlogIndexEntry[] {
  const current = blogIndexEntries.find((e) => e.slug === slug);
  if (!current) return [];
  const tags = new Set(current.tags ?? []);

  return blogIndexEntries
    .filter((e) => e.slug !== slug)
    .map((entry) => {
      let score = 0;
      if (entry.category && entry.category === current.category) score += 3;
      for (const tag of entry.tags ?? []) if (tags.has(tag)) score += 1;
      return { entry, score };
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.entry.slug.localeCompare(b.entry.slug))
    .slice(0, limit)
    .map((x) => x.entry);
}

/**
 * Yayın sırasına göre önceki ve sonraki yazı.
 *
 * Liste tarihe göre yeniden eskiye sıralı olduğu için dizideki bir önceki
 * kayıt daha yeni yazıdır; okuyucuya "sonraki" olarak o gösterilir.
 */
export function getAdjacentEntries(slug: string): {
  newer?: BlogIndexEntry;
  older?: BlogIndexEntry;
} {
  const index = blogIndexEntries.findIndex((entry) => entry.slug === slug);
  if (index === -1) return {};

  return {
    newer: index > 0 ? blogIndexEntries[index - 1] : undefined,
    older: index < blogIndexEntries.length - 1 ? blogIndexEntries[index + 1] : undefined,
  };
}
