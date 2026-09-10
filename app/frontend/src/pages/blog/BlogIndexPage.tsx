import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getBlogRoute } from '@/lib/blogRoute';
import { blogIndexCategories, blogIndexEntries } from '@/lib/blogIndex';
import { usePanelPosts } from '@/lib/panelPosts';

const ALL_CATEGORIES = '__all__';

/** Listede gösterilen ortak yazı biçimi. */
interface ListedPost {
  slug: string;
  title: string;
  description: string;
  category?: string;
  date?: string;
  tags?: string[];
}

const BlogIndexPage = () => {
  const { t } = useTranslation();
  const [activeCategory, setActiveCategory] = useState<string>(ALL_CATEGORIES);
  const { panelPosts } = usePanelPosts();

  /**
   * Markdown yazıları ile panelden yayımlananlar tek listede.
   *
   * Daha önce iki ayrı blog listesi vardı: prerender bu bileşeni basıyor,
   * istemci ise API'den çeken başka bir bileşeni hidrate ediyordu. Google'ın
   * gördüğü sayfa ile ziyaretçinin gördüğü sayfa farklıydı. Artık ikisi de
   * burası; markdown yazıları statik HTML'de gelir, panel yazıları sayfa
   * yüklendikten sonra eklenir. Aynı slug iki kaynakta varsa markdown kazanır
   * (prerender edilen sürüm o).
   */
  const allPosts = useMemo<ListedPost[]>(() => {
    const markdown: ListedPost[] = blogIndexEntries.map((post) => ({
      slug: post.slug,
      title: post.title,
      description: post.description,
      category: post.category,
      date: post.date,
      tags: post.tags,
    }));

    const seen = new Set(markdown.map((p) => p.slug));
    const fromPanel: ListedPost[] = panelPosts
      .filter((post) => !seen.has(post.slug))
      .map((post) => ({
        slug: post.slug,
        title: post.title,
        description: post.excerpt ?? '',
        category: post.category,
        date: post.created_at?.slice(0, 10),
      }));

    return [...markdown, ...fromPanel].sort((a, b) => {
      const at = a.date ? Date.parse(a.date) : NaN;
      const bt = b.date ? Date.parse(b.date) : NaN;
      if (!Number.isNaN(at) && !Number.isNaN(bt) && at !== bt) return bt - at;
      if (!Number.isNaN(at) && Number.isNaN(bt)) return -1;
      if (Number.isNaN(at) && !Number.isNaN(bt)) return 1;
      return a.slug.localeCompare(b.slug);
    });
  }, [panelPosts]);

  const categories = useMemo(() => {
    const all = new Set<string>(blogIndexCategories);
    panelPosts.forEach((post) => post.category && all.add(post.category));
    return Array.from(all).sort((a, b) => a.localeCompare(b, 'tr'));
  }, [panelPosts]);

  const visiblePosts = useMemo(() => {
    if (activeCategory === ALL_CATEGORIES) return allPosts;
    return allPosts.filter((post) => post.category === activeCategory);
  }, [activeCategory, allPosts]);

  return (
  <main className="min-h-screen bg-[#05010a] text-[#ece6ff]">
    <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_20%_0%,rgba(139,61,255,0.25),transparent_45%),radial-gradient(circle_at_80%_10%,rgba(212,165,255,0.14),transparent_40%)]" />
    <section className="mx-auto max-w-5xl px-6 py-16 sm:py-24">
      <div className="max-w-3xl space-y-5">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-purple-400">
          Blog
        </p>
        <h1 className="text-4xl font-bold leading-tight text-white sm:text-5xl">
          {t('ui.blogIndexTitle')}
        </h1>
        <p className="text-lg leading-8 text-[#b9a9d6]">
          {t('ui.blogIndexDesc')}
        </p>
        <Link
          to="/"
          className="inline-flex text-sm font-semibold text-purple-300 underline underline-offset-4 hover:text-pink-300"
        >
          &larr; {t('ui.backHome')}
        </Link>
      </div>

      {categories.length > 0 ? (
        <div className="mt-10 flex flex-wrap gap-3" role="group" aria-label={t('portfolio.all')}>
          <button
            type="button"
            onClick={() => setActiveCategory(ALL_CATEGORIES)}
            aria-pressed={activeCategory === ALL_CATEGORIES}
            className={`rounded-full border px-4 py-2 text-sm font-semibold transition-colors ${
              activeCategory === ALL_CATEGORIES
                ? 'border-purple-400 bg-purple-500/20 text-white'
                : 'border-white/10 bg-white/[0.03] text-[#b9a9d6] hover:border-purple-500/40 hover:text-white'
            }`}
          >
            {t('portfolio.all')}
          </button>
          {categories.map((category) => (
            <button
              key={category}
              type="button"
              onClick={() => setActiveCategory(category)}
              aria-pressed={activeCategory === category}
              className={`rounded-full border px-4 py-2 text-sm font-semibold transition-colors ${
                activeCategory === category
                  ? 'border-purple-400 bg-purple-500/20 text-white'
                  : 'border-white/10 bg-white/[0.03] text-[#b9a9d6] hover:border-purple-500/40 hover:text-white'
              }`}
            >
              {category}
            </button>
          ))}
        </div>
      ) : null}

      <div className="mt-12 grid gap-6">
        {visiblePosts.length > 0 ? (
          visiblePosts.map((post) => (
            <article
              key={post.slug}
              className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:border-purple-500/40"
            >
              <div className="flex flex-wrap items-center gap-3 text-sm text-[#9d8cbf]">
                {post.date ? <span>{post.date}</span> : null}
                {post.tags?.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-purple-500/15 px-3 py-1 text-purple-200"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <h2 className="mt-4 text-2xl font-semibold text-white">
                <Link
                  className="hover:text-purple-300"
                  to={getBlogRoute(post.slug)}
                >
                  {post.title}
                </Link>
              </h2>
              <p className="mt-3 text-base leading-7 text-[#b9a9d6]">
                {post.description}
              </p>
              <Link
                to={getBlogRoute(post.slug)}
                className="mt-5 inline-flex text-sm font-semibold text-purple-300 underline underline-offset-4 hover:text-pink-300"
              >
                {t('ui.readArticle')}
              </Link>
            </article>
          ))
        ) : (
          <section className="rounded-[2rem] border border-dashed border-purple-500/30 bg-white/[0.02] p-8">
            <h2 className="text-2xl font-semibold text-white">
              {t('ui.noPostsTitle')}
            </h2>
            <p className="mt-3 max-w-2xl text-base leading-7 text-[#b9a9d6]">
              {t('ui.noPostsDesc')}
            </p>
          </section>
        )}
      </div>
    </section>
  </main>
  );
};

export default BlogIndexPage;
