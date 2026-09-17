import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

type BlogArticleLayoutProps = {
  title: string;
  description?: string;
  /** Kapak görseli — WebP, 1200x630. */
  coverImage?: string;
  coverAlt?: string;
  children: React.ReactNode;
};

const BlogArticleLayout = ({
  title,
  description,
  coverImage,
  coverAlt,
  children,
}: BlogArticleLayoutProps) => {
  const { t } = useTranslation();

  return (
  <main className="min-h-screen bg-[#05010a] text-[#ece6ff]">
    <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_20%_0%,rgba(139,61,255,0.25),transparent_45%),radial-gradient(circle_at_80%_10%,rgba(212,165,255,0.14),transparent_40%)]" />
    <div className="mx-auto max-w-4xl px-6 pt-10">
      <Link
        to="/blog"
        className="text-sm text-purple-300 underline-offset-4 transition-colors hover:text-pink-300 hover:underline"
      >
        &larr; {t('ui.backToBlog')}
      </Link>
    </div>
    <article className="mx-auto max-w-3xl px-6 py-12">
      <header className="border-b border-white/10 pb-10">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-purple-400">
          {t('ui.blogPost')}
        </p>
        <h1 className="mt-4 text-4xl font-bold leading-tight text-white sm:text-5xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-5 max-w-2xl text-lg leading-8 text-[#b9a9d6]">
            {description}
          </p>
        ) : null}

        {coverImage ? (
          /*
           * Kapak görseli. width/height verilmesi düzen kaymasını (CLS)
           * önlüyor; yazının ilk ekranında yer aldığı için lazy değil,
           * yüksek öncelikli yükleniyor.
           */
          <img
            src={coverImage}
            alt={coverAlt ?? ''}
            width={1200}
            height={630}
            loading="eager"
            fetchPriority="high"
            decoding="async"
            className="mt-8 aspect-[1200/630] w-full max-w-full rounded-2xl border border-white/10 object-cover"
          />
        ) : null}
      </header>

      <div className="mt-10">{children}</div>
    </article>
  </main>
  );
};

export default BlogArticleLayout;