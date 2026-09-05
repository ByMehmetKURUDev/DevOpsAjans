import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Calendar, ArrowRight, Loader2, FileText } from 'lucide-react';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';
import { blogPosts as seoArticles, getBlogRoute } from '@/lib/blog';

const client = createClient();

interface DbBlogPost {
  id: number | string;
  title: string;
  slug: string;
  excerpt?: string;
  content?: string;
  cover_image?: string;
  author?: string;
  category?: string;
  published?: boolean;
  created_at?: string;
}

/** Kategori adlarını i18n anahtarlarına eşler. */
const BLOG_CATEGORY_KEYS: Record<string, string> = {
  Website: 'ui.catWebsite',
  'E-Ticaret': 'ui.catEcommerce',
  SaaS: 'ui.catSaas',
  'Mobil Uygulama': 'ui.catMobile',
  Reklam: 'ui.catAds',
  SEO: 'ui.catSeo',
};

const BLOG_CATEGORIES = [
  'all',
  'Website',
  'E-Ticaret',
  'SaaS',
  'Mobil Uygulama',
  'Reklam',
  'SEO',
];

export default function Blog() {
  const { t } = useTranslation();
  const [posts, setPosts] = useState<DbBlogPost[]>([]);
  const [selected, setSelected] = useState<DbBlogPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeCat, setActiveCat] = useState('all');

  useEffect(() => {
    let cancelled = false;
    client.entities.blog_posts
      .query({ query: { published: true }, sort: '-created_at', limit: 50 })
      .then((res) => {
        if (cancelled) return;
        setPosts((res?.data?.items ?? []) as DbBlogPost[]);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || t('ui.loadError'));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredPosts = useMemo(
    () => posts.filter((p) => activeCat === 'all' || p.category === activeCat),
    [posts, activeCat]
  );

  const showSeoArticles = activeCat === 'all' || activeCat === 'SEO';

  if (selected) {
    return (
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <button
          onClick={() => setSelected(null)}
          className="text-sm text-purple-400 hover:text-purple-300 mb-8 inline-flex items-center gap-2"
        >
          &larr; {t('blog.backToAll')}
        </button>
        {selected.cover_image && (
          <div className="rounded-2xl overflow-hidden mb-8 aspect-[16/9]">
            <img
              src={selected.cover_image}
              alt={selected.title}
              className="w-full h-full object-cover"
            />
          </div>
        )}
        <div className="mb-6">
          {selected.category && (
            <span className="text-xs uppercase tracking-widest text-purple-400">
              {selected.category}
            </span>
          )}
          <h1 className="text-4xl md:text-5xl font-bold mt-3 leading-tight">
            {selected.title}
          </h1>
          <div className="flex items-center gap-4 mt-4 text-sm text-muted-foreground">
            {selected.author && <span>{selected.author}</span>}
            {selected.created_at && (
              <span className="flex items-center gap-1.5">
                <Calendar className="h-3.5 w-3.5" />
                {new Date(selected.created_at).toLocaleDateString('tr-TR')}
              </span>
            )}
          </div>
        </div>
        {selected.excerpt && (
          <p className="text-xl text-muted-foreground leading-relaxed mb-6 italic border-l-2 border-purple-500 pl-4">
            {selected.excerpt}
          </p>
        )}
        <div className="max-w-none">
          {(selected.content || '').split('\n\n').map((para, i) => (
            <p key={i} className="mb-4 text-muted-foreground leading-relaxed">
              {para}
            </p>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <section className="py-24 md:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-xs uppercase tracking-[0.3em] text-purple-400 mb-4">
            {t('blog.sectionTag')}
          </p>
          <h1 className="text-5xl md:text-7xl font-bold leading-[1.05] mb-6 max-w-3xl">
            {t('blog.title')}{' '}
            <span className="gradient-text">{t('blog.titleHighlight')}</span>
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl">
            {t('blog.desc')}
          </p>
        </div>
      </section>

      {/* Category filter */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mb-10">
        <div className="flex flex-wrap gap-2">
          {BLOG_CATEGORIES.map((cat) => {
            const active = cat === activeCat;
            return (
              <button
                key={cat}
                onClick={() => setActiveCat(cat)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                  active
                    ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white'
                    : 'glass text-muted-foreground hover:text-foreground hover:border-purple-500/30'
                }`}
              >
                {cat === 'all' ? t('portfolio.all') : t(BLOG_CATEGORY_KEYS[cat] ?? '', { defaultValue: cat })}
              </button>
            );
          })}
        </div>
      </div>

      {/* SEO uzun-form makaleler */}
      {showSeoArticles && seoArticles.length > 0 && (
        <section className="pb-16">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3 mb-6">
              <FileText className="h-5 w-5 text-purple-400" />
              <h2 className="text-2xl font-bold">{t('ui.guideArticles')}</h2>
            </div>
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {seoArticles.map((article) => (
                <Link
                  key={article.slug}
                  to={getBlogRoute(article.slug)}
                  className="group rounded-2xl glass p-6 hover:border-purple-500/40 transition-all duration-500 hover:-translate-y-1 flex flex-col"
                >
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <span className="text-[10px] uppercase tracking-widest text-purple-400">
                      {t('ui.guide')}
                    </span>
                    {article.frontmatter.date && (
                      <span className="text-[10px] text-muted-foreground">
                        {article.frontmatter.date}
                      </span>
                    )}
                  </div>
                  <h3 className="text-xl font-semibold mb-3 leading-tight group-hover:gradient-text transition-all">
                    {article.title}
                  </h3>
                  <p className="text-sm text-muted-foreground line-clamp-4 mb-5 flex-1">
                    {article.description}
                  </p>
                  <span className="inline-flex items-center gap-1 text-sm text-purple-400 group-hover:text-pink-400 transition-colors">
                    {t('ui.readArticle')} <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <section className="pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {loading ? (
            <div className="py-24 flex items-center justify-center text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin mr-3" />
              {t('blog.loading')}
            </div>
          ) : error ? (
            <div className="py-24 text-center text-destructive">{error}</div>
          ) : filteredPosts.length === 0 ? (
            !showSeoArticles && (
              <div className="py-24 text-center text-muted-foreground">
                {t('blog.empty')}
              </div>
            )
          ) : (
            <>
              <h2 className="text-2xl font-bold mb-6">{t('ui.recentArticles')}</h2>
              <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
                {filteredPosts.map((post) => (
                  <article
                    key={post.id}
                    onClick={() => setSelected(post)}
                    className="group cursor-pointer rounded-2xl overflow-hidden glass hover:border-purple-500/40 transition-all duration-500 hover:-translate-y-1"
                  >
                    <div className="relative aspect-[16/9] overflow-hidden bg-gradient-to-br from-purple-950/40 to-pink-950/40">
                      {post.cover_image ? (
                        <img
                          src={post.cover_image}
                          alt={post.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-4xl gradient-text font-bold">
                          {post.title.charAt(0)}
                        </div>
                      )}
                    </div>
                    <div className="p-6">
                      {post.category && (
                        <span className="text-[10px] uppercase tracking-widest text-purple-400">
                          {post.category}
                        </span>
                      )}
                      <h3 className="text-xl font-semibold my-3 group-hover:gradient-text transition-all leading-tight">
                        {post.title}
                      </h3>
                      <p className="text-sm text-muted-foreground line-clamp-3 mb-5">
                        {post.excerpt}
                      </p>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{post.author}</span>
                        <span className="inline-flex items-center gap-1 text-purple-400 group-hover:text-pink-400 transition-colors">
                          {t('blog.read')} <ArrowRight className="h-3 w-3" />
                        </span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}