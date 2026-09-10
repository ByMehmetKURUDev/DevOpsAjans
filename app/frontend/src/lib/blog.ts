import { parse as parseYaml } from 'yaml';

type FrontmatterValue = string | string[];

type BlogFrontmatter = Record<string, FrontmatterValue | undefined> & {
  title?: string;
  description?: string;
  date?: string;
  tags?: string[];
};

type BlogPost = {
  slug: string;
  markdown: string;
  title: string;
  description: string;
  category?: string;
  frontmatter: BlogFrontmatter;
};

type SeoMeta = {
  title: string;
  description: string;
  keywords?: string;
  lang?: string;
  url?: string;
  siteName: string;
  ogTitle: string;
  ogDescription: string;
  ogImage?: string;
  ogImageAlt?: string;
  ogType: string;
  twitterCard: string;
  twitterSite?: string;
  twitterCreator?: string;
  twitterTitle: string;
  twitterDescription: string;
  twitterImage?: string;
  twitterImageAlt?: string;
  publishedTime?: string;
  tags?: string[];
};

const markdownModules = import.meta.glob(
  ['../../seo/content/**/*.md'],
  {
    query: '?raw',
    import: 'default',
    eager: true,
  },
) as Record<string, string>;

function parseFrontmatter(markdown: string) {
  if (!markdown.startsWith('---')) {
    return {
      data: {} satisfies BlogFrontmatter,
      content: markdown,
    };
  }

  const frontmatterMatch = markdown.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!frontmatterMatch) {
    return {
      data: {} satisfies BlogFrontmatter,
      content: markdown,
    };
  }

  const rawFrontmatter = frontmatterMatch[1];
  const content = markdown.slice(frontmatterMatch[0].length);

  try {
    const parsed = parseYaml(rawFrontmatter);
    const data = normalizeFrontmatter(parsed);

    return { data, content };
  } catch (error) {
    console.warn(
      'Failed to parse blog frontmatter, falling back to raw content',
      error,
    );

    return {
      data: {} satisfies BlogFrontmatter,
      content: markdown,
    };
  }
}

function normalizeFrontmatter(value: unknown): BlogFrontmatter {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  const entries = Object.entries(value as Record<string, unknown>).map(
    ([key, entryValue]) => {
      if (Array.isArray(entryValue)) {
        return [
          key,
          entryValue
            .map((item) => String(item).trim())
            .filter(Boolean),
        ] as const;
      }

      if (entryValue === null || typeof entryValue === 'undefined') {
        return [key, undefined] as const;
      }

      return [key, String(entryValue).trim()] as const;
    },
  );

  return Object.fromEntries(entries) as BlogFrontmatter;
}

function titleFromSlug(slug: string) {
  return slug
    .split('-')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function descriptionFromMarkdown(markdown: string) {
  const plainText = markdown
    .replace(/^#+\s+/gm, '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/[*_`>#-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  return plainText.slice(0, 160);
}

function normalizeSlug(filePath: string) {
  return filePath
    .replace(/\\/g, '/')
    .replace(/^.*\/seo\/content\//, '')
    .replace(/\/index\.md$/, '')
    .replace(/\.md$/, '');
}

function compareBlogPosts(a: BlogPost, b: BlogPost) {
  const aTime = a.frontmatter.date ? Date.parse(a.frontmatter.date) : NaN;
  const bTime = b.frontmatter.date ? Date.parse(b.frontmatter.date) : NaN;

  if (!Number.isNaN(aTime) && !Number.isNaN(bTime) && aTime !== bTime) {
    return bTime - aTime;
  }

  if (!Number.isNaN(aTime) && Number.isNaN(bTime)) {
    return -1;
  }

  if (Number.isNaN(aTime) && !Number.isNaN(bTime)) {
    return 1;
  }

  return a.slug.localeCompare(b.slug);
}

const blogPosts: BlogPost[] = Object.entries(markdownModules)
  .map(([filePath, rawMarkdown]) => {
    const { data, content } = parseFrontmatter(rawMarkdown);
    const slug = normalizeSlug(filePath);
    const frontmatter = data;
    const title = frontmatter.title || titleFromSlug(slug.split('/').pop() || slug);
    const description = frontmatter.description || descriptionFromMarkdown(content);
    const category =
      frontmatterString(frontmatter, 'category') ?? frontmatter.tags?.[0];

    return {
      slug,
      markdown: content,
      title,
      description,
      category,
      frontmatter,
    };
  })
  .sort(compareBlogPosts);

const blogCategories: string[] = Array.from(
  new Set(
    blogPosts
      .map((post) => post.category)
      .filter((category): category is string => Boolean(category)),
  ),
).sort((a, b) => a.localeCompare(b, 'tr'));

function getBlogPost(slug: string) {
  return blogPosts.find((post) => post.slug === slug);
}

function getBlogRoute(slug: string) {
  return `/blog/${slug}/`.replace(/\/+/g, '/');
}

function getSiteDomainUrl() {
  const configuredUrl = import.meta.env.VITE_SITE_URL?.trim();
  return configuredUrl ? configuredUrl.replace(/\/+$/, '') : undefined;
}

function getSiteName() {
  return import.meta.env.VITE_APP_TITLE?.trim() || 'By Mehmet KURU Dev';
}

/**
 * Twitter hesabı bilinmiyorsa etiket hiç üretilmiyor. Önceki şablon
 * varsayılanı olan `@atoms` yanlış bir hesaba atıf yapıyordu.
 */
function getTwitterSiteHandle() {
  return import.meta.env.VITE_TWITTER_SITE?.trim() || undefined;
}

function getTwitterCreatorHandle() {
  return import.meta.env.VITE_TWITTER_CREATOR?.trim() || getTwitterSiteHandle();
}

function getAbsoluteUrl(pathname: string) {
  const siteDomainUrl = getSiteDomainUrl();
  if (!siteDomainUrl) {
    return undefined;
  }

  const normalizedPath = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `${siteDomainUrl}${normalizedPath}`;
}

function hasBlogPosts() {
  return blogPosts.length > 0;
}

function frontmatterString(
  frontmatter: BlogFrontmatter,
  key: string,
): string | undefined {
  const value = frontmatter[key];
  return typeof value === 'string' ? value : undefined;
}

function frontmatterStringList(
  frontmatter: BlogFrontmatter,
  key: string,
): string[] | undefined {
  const value = frontmatter[key];

  if (Array.isArray(value)) {
    return value.filter((entry): entry is string => typeof entry === 'string');
  }

  if (typeof value === 'string') {
    return value
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean);
  }

  return undefined;
}

function getPostSeoMeta(post?: BlogPost | null): SeoMeta {
  const siteName = getSiteName();
  const twitterSiteHandle = getTwitterSiteHandle();
  const twitterCreatorHandle = getTwitterCreatorHandle();
  const fallbackTitle = 'Blog: SEO, Reklam Ölçümleme ve Web Geliştirme Rehberleri';
  const fallbackDescription =
    'Teknik SEO, Google Ads ve GA4 ölçümleme, Customer 360 veri yönetimi ve web geliştirme üzerine uygulamaya dönük rehberler.';

  if (!post) {
    const fallbackUrl = getAbsoluteUrl('/blog/');
    return {
      title: fallbackTitle,
      description: fallbackDescription,
      url: fallbackUrl,
      siteName,
      ogTitle: fallbackTitle,
      ogDescription: fallbackDescription,
      ogImageAlt: siteName,
      ogType: 'website',
      twitterCard: 'summary_large_image',
      twitterSite: twitterSiteHandle,
      twitterCreator: twitterCreatorHandle,
      twitterTitle: fallbackTitle,
      twitterDescription: fallbackDescription,
    };
  }

  const title = `${post.title} | Blog`;
  const description = post.description;
  const url =
    frontmatterString(post.frontmatter, 'og_url') ??
    getAbsoluteUrl(getBlogRoute(post.slug));
  const keywordsList =
    frontmatterStringList(post.frontmatter, 'keywords') ?? post.frontmatter.tags;
  const ogImage =
    frontmatterString(post.frontmatter, 'og_image') ??
    frontmatterString(post.frontmatter, 'hero_image');
  const imageAlt =
    frontmatterString(post.frontmatter, 'og_image_alt') ??
    frontmatterString(post.frontmatter, 'twitter_image_alt') ??
    post.title;
  const twitterImage =
    frontmatterString(post.frontmatter, 'twitter_image') ?? ogImage;

  return {
    title,
    description,
    keywords: keywordsList?.join(', '),
    lang: frontmatterString(post.frontmatter, 'lang'),
    url,
    siteName: frontmatterString(post.frontmatter, 'og_site_name') ?? siteName,
    ogTitle: frontmatterString(post.frontmatter, 'og_title') ?? title,
    ogDescription:
      frontmatterString(post.frontmatter, 'og_description') ?? description,
    ogImage,
    ogImageAlt: imageAlt,
    ogType: frontmatterString(post.frontmatter, 'og_type') ?? 'article',
    twitterCard:
      frontmatterString(post.frontmatter, 'twitter_card') ??
      (twitterImage ? 'summary_large_image' : 'summary'),
    twitterSite:
      frontmatterString(post.frontmatter, 'twitter_site') ?? twitterSiteHandle,
    twitterCreator:
      frontmatterString(post.frontmatter, 'twitter_creator') ??
      twitterCreatorHandle,
    twitterTitle:
      frontmatterString(post.frontmatter, 'twitter_title') ?? title,
    twitterDescription:
      frontmatterString(post.frontmatter, 'twitter_description') ?? description,
    twitterImage,
    twitterImageAlt: imageAlt,
    publishedTime: frontmatterString(post.frontmatter, 'date'),
    tags: post.frontmatter.tags,
  };
}


/** Yazının gövdesindeki "Sık Sorulan Sorular" bölümünü ayrıştırır. */
type FaqEntry = { question: string; answer: string };

function extractFaq(markdown: string): FaqEntry[] {
  // Bölüm sınırları satır satır bulunur. Tek bir regex ile denendiğinde `m`
  // bayrağı `$`i satır sonuna bağlıyor ve bölüm ilk satırda kesiliyordu —
  // her yazıdan yalnızca ilk soru çıkıyordu.
  const lines = markdown.split('\n');
  const start = lines.findIndex((line) =>
    /^##\s*(?:Sık Sorulan Sorular|SSS)\s*$/.test(line.trim()),
  );
  if (start === -1) return [];

  let end = lines.length;
  for (let i = start + 1; i < lines.length; i += 1) {
    if (/^##\s/.test(lines[i])) {
      end = i;
      break;
    }
  }

  const section = lines.slice(start + 1, end).join('\n');
  const entries: FaqEntry[] = [];
  // Biçim: **Soru?** Cevap
  const pattern = /\*\*(.+?)\*\*\s*([\s\S]*?)(?=\n\s*\*\*|$)/g;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(section)) !== null) {
    const question = match[1].trim();
    const answer = match[2].replace(/\s+/g, ' ').trim();
    if (question && answer) entries.push({ question, answer });
  }

  return entries;
}

/**
 * İlgili yazılar.
 *
 * Önce aynı kategoriden, sonra ortak etiketi olanlardan seçilir. 61 yazı
 * birbirine hiç link vermiyordu; konu kümesi içindeki bağlantılar hem
 * okuyucuyu hem tarayıcıyı yazılar arasında dolaştırır.
 */
function getRelatedPosts(post: BlogPost, limit = 3): BlogPost[] {
  const tags = new Set(post.frontmatter.tags ?? []);

  const scored = blogPosts
    .filter((candidate) => candidate.slug !== post.slug)
    .map((candidate) => {
      let score = 0;
      if (candidate.category && candidate.category === post.category) score += 3;
      for (const tag of candidate.frontmatter.tags ?? []) {
        if (tags.has(tag)) score += 1;
      }
      return { candidate, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.candidate.slug.localeCompare(b.candidate.slug));

  return scored.slice(0, limit).map((entry) => entry.candidate);
}

export {
  blogCategories,
  blogPosts,
  extractFaq,
  getBlogPost,
  getBlogRoute,
  getPostSeoMeta,
  getRelatedPosts,
  hasBlogPosts,
};
export type { BlogFrontmatter, BlogPost, FaqEntry, SeoMeta };
