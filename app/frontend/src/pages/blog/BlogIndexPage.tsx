import { useEffect, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { getBlogRoute } from '@/lib/blogRoute';
import { blogIndexCategories, blogIndexEntries } from '@/lib/blogIndex';
import { usePanelPosts } from '@/lib/panelPosts';
import Pagination from '@/components/blog/Pagination';

const ALL_CATEGORIES = '__all__';

/** Sayfa başına yazı sayısı. */
const PER_PAGE = 10;

/** Sıralama seçenekleri. Anahtarlar adres çubuğunda görünür. */
const SORT_OPTIONS = [
  { value: 'yeni', labelKey: 'ui.sortNewest' },
  { value: 'eski', labelKey: 'ui.sortOldest' },
  { value: 'baslik', labelKey: 'ui.sortTitleAsc' },
] as const;

type SortValue = (typeof SORT_OPTIONS)[number]['value'];

const DEFAULT_SORT: SortValue = 'yeni';

function parseDate(value?: string): number {
  if (!value) return Number.NaN;
  return Date.parse(value);
}

/** Tarihi olmayan yazılar her zaman sona düşer; sıralama yönü onları taşımaz. */
function byDate(a: { date?: string; slug: string }, b: { date?: string; slug: string }, newestFirst: boolean) {
  const at = parseDate(a.date);
  const bt = parseDate(b.date);
  if (Number.isNaN(at) && Number.isNaN(bt)) return a.slug.localeCompare(b.slug);
  if (Number.isNaN(at)) return 1;
  if (Number.isNaN(bt)) return -1;
  if (at === bt) return a.slug.localeCompare(b.slug);
  return newestFirst ? bt - at : at - bt;
}

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
  const { panelPosts } = usePanelPosts();

  /**
   * Kategori, sıralama ve sayfa adres çubuğunda tutulur.
   *
   * Bileşen state'i yerine sorgu parametresi kullanılıyor: böylece üçüncü
   * sayfanın bağlantısı paylaşılabiliyor, tarayıcının geri tuşu çalışıyor
   * ve sayfa numaraları gerçek `href` taşıyan bağlantılar olabiliyor.
   */
  const [params, setParams] = useSearchParams();
  const activeCategory = params.get('kategori') || ALL_CATEGORIES;
  const sort = (SORT_OPTIONS.find((o) => o.value === params.get('sirala'))?.value ??
    DEFAULT_SORT) as SortValue;
  const requestedPage = Math.max(1, Number.parseInt(params.get('sayfa') ?? '1', 10) || 1);

  /** Parametreyi günceller; varsayılan değerleri adrese yazmaz. */
  const updateParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([key, value]) => {
      if (value === null) next.delete(key);
      else next.set(key, value);
    });
    setParams(next, { replace: false });
  };

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

    return [...markdown, ...fromPanel];
  }, [panelPosts]);

  const categories = useMemo(() => {
    const all = new Set<string>(blogIndexCategories);
    panelPosts.forEach((post) => post.category && all.add(post.category));
    return Array.from(all).sort((a, b) => a.localeCompare(b, 'tr'));
  }, [panelPosts]);

  /** Kategori süzgeci + seçilen sıralama. */
  const filteredPosts = useMemo(() => {
    const list =
      activeCategory === ALL_CATEGORIES
        ? [...allPosts]
        : allPosts.filter((post) => post.category === activeCategory);

    if (sort === 'baslik') {
      return list.sort((a, b) => a.title.localeCompare(b.title, 'tr'));
    }
    return list.sort((a, b) => byDate(a, b, sort === 'yeni'));
  }, [activeCategory, allPosts, sort]);

  const pageCount = Math.max(1, Math.ceil(filteredPosts.length / PER_PAGE));
  const page = Math.min(requestedPage, pageCount);
  const visiblePosts = filteredPosts.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  /**
   * Panel yazıları sonradan yüklendiğinde toplam sayfa sayısı düşebiliyor;
   * o durumda adres çubuğundaki sayfa numarası da geçerli aralığa çekilir.
   */
  useEffect(() => {
    if (requestedPage > pageCount) {
      updateParams({ sayfa: pageCount === 1 ? null : String(pageCount) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageCount, requestedPage]);

  const hrefFor = (target: number) => {
    const next = new URLSearchParams(params);
    if (target <= 1) next.delete('sayfa');
    else next.set('sayfa', String(target));
    const query = next.toString();
    return query ? `/blog?${query}` : '/blog';
  };

  const goToPage = (target: number) => {
    updateParams({ sayfa: target <= 1 ? null : String(target) });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const selectCategory = (category: string) => {
    // Kategori değişince eski sayfa numarası anlamsız kalıyor, sıfırlanır.
    updateParams({
      kategori: category === ALL_CATEGORIES ? null : category,
      sayfa: null,
    });
  };

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
            onClick={() => selectCategory(ALL_CATEGORIES)}
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
              onClick={() => selectCategory(category)}
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

      {/* Sıralama ve sayaç: liste ile süzgeçler arasında tek satır. */}
      {filteredPosts.length > 0 ? (
        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-b border-white/5 pb-4">
          <p className="text-sm text-[#9d8cbf]">
            {t('ui.postCount', { total: filteredPosts.length, page, pages: pageCount })}
          </p>
          <label className="flex items-center gap-2 text-sm text-[#9d8cbf]">
            <span>{t('ui.sortLabel')}</span>
            <select
              value={sort}
              onChange={(event) =>
                updateParams({
                  sirala: event.target.value === DEFAULT_SORT ? null : event.target.value,
                  sayfa: null,
                })
              }
              className="rounded-xl border border-white/10 bg-[#120b1f] px-3 py-2 text-sm font-semibold text-white outline-none transition-colors hover:border-purple-500/40 focus:border-purple-400"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}

      <div className="mt-8 grid gap-6">
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

      <Pagination page={page} pageCount={pageCount} hrefFor={hrefFor} onNavigate={goToPage} />

      {/*
        Sayfalama okuması kolaylaştırıyor ama bir yan etkisi var: dizinin
        HTML'inde artık 70 değil 10 yazı bağlantısı kalıyor, kalan yazılar
        dizinden iç link almıyor. Aşağıdaki katlanmış arşiv bunu telafi
        ediyor — kapalı `details` de HTML'de duruyor, tarayıcı da arama motoru
        da bütün yazıları buradan görüyor.
      */}
      {filteredPosts.length > PER_PAGE ? (
        <details className="mt-12 rounded-3xl border border-white/10 bg-white/[0.02] p-6">
          <summary className="cursor-pointer text-sm font-semibold text-purple-300 hover:text-pink-300">
            {t('ui.postCount', { total: filteredPosts.length, page, pages: pageCount })}
            {' — '}
            {t('portfolio.all')}
          </summary>
          <ul className="mt-5 grid gap-2 sm:grid-cols-2">
            {filteredPosts.map((post) => (
              <li key={`arsiv-${post.slug}`}>
                <Link
                  to={getBlogRoute(post.slug)}
                  className="text-sm leading-6 text-[#b9a9d6] underline-offset-4 hover:text-white hover:underline"
                >
                  {post.title}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  </main>
  );
};

export default BlogIndexPage;
