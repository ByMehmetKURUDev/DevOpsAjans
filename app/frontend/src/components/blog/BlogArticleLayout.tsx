import { Link } from 'react-router-dom';

type BlogArticleLayoutProps = {
  title: string;
  description?: string;
  children: React.ReactNode;
};

const BlogArticleLayout = ({
  title,
  description,
  children,
}: BlogArticleLayoutProps) => (
  <main className="min-h-screen bg-[#05010a] text-[#ece6ff]">
    <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_20%_0%,rgba(139,61,255,0.25),transparent_45%),radial-gradient(circle_at_80%_10%,rgba(212,165,255,0.14),transparent_40%)]" />
    <div className="mx-auto max-w-4xl px-6 pt-10">
      <Link
        to="/blog"
        className="text-sm text-purple-300 underline-offset-4 transition-colors hover:text-pink-300 hover:underline"
      >
        &larr; Blog'a dön
      </Link>
    </div>
    <article className="mx-auto max-w-3xl px-6 py-12">
      <header className="border-b border-white/10 pb-10">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-purple-400">
          Blog Yazısı
        </p>
        <h1 className="mt-4 text-4xl font-bold leading-tight text-white sm:text-5xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-5 max-w-2xl text-lg leading-8 text-[#b9a9d6]">
            {description}
          </p>
        ) : null}
      </header>

      <div className="mt-10">{children}</div>
    </article>
  </main>
);

export default BlogArticleLayout;