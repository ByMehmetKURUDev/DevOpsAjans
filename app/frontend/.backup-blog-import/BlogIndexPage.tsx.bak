import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { blogPosts, getBlogRoute } from '@/lib/blog';

const BlogIndexPage = () => {
  const { t } = useTranslation();

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

      <div className="mt-12 grid gap-6">
        {blogPosts.length > 0 ? (
          blogPosts.map((post) => (
            <article
              key={post.slug}
              className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:border-purple-500/40"
            >
              <div className="flex flex-wrap items-center gap-3 text-sm text-[#9d8cbf]">
                {post.frontmatter.date ? (
                  <span>{post.frontmatter.date}</span>
                ) : null}
                {post.frontmatter.tags?.map((tag) => (
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