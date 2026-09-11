import { useEffect, useState } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import BlogArticleLayout from '@/components/blog/BlogArticleLayout';
import MarkdownArticle, { getHeadings } from '@/components/blog/MarkdownArticle';
import PostNavigation from '@/components/blog/PostNavigation';
import RelatedPosts from '@/components/blog/RelatedPosts';
import ShareButtons from '@/components/ShareButtons';
import TableOfContents from '@/components/blog/TableOfContents';
import { getBlogPost, getPostSeoMeta } from '@/lib/blog';
import { getAdjacentEntries, getRelatedEntries } from '@/lib/blogIndex';
import { fetchPanelPost, type PanelPost } from '@/lib/panelPosts';
import { SITE_URL } from '../../../prerender/site.js';

function getSlugFromPathname(pathname: string) {
  return pathname
    .replace(/^\/blog\/?/, '')
    .replace(/\/+$/, '')
    .replace(/^\/+/, '');
}

function ensureMetaTag(
  attribute: 'name' | 'property',
  value: string,
) {
  let tag = document.head.querySelector(
    `meta[${attribute}="${value}"]`,
  ) as HTMLMetaElement | null;

  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute(attribute, value);
    document.head.appendChild(tag);
  }

  return tag;
}

function getCurrentPageUrl(pathname: string) {
  if (typeof window === 'undefined') {
    return undefined;
  }

  return `${window.location.origin}${pathname}`;
}

const BlogPostPage = () => {
  const location = useLocation();
  const slug = getSlugFromPathname(location.pathname);
  const post = slug === '*' ? null : getBlogPost(slug);

  /**
   * Panelden yayımlanan yazılar için geri düşüş.
   *
   * Bu yazılar build sırasında erişilemediği için prerender edilemiyor;
   * markdown'da bulunmayan bir slug geldiğinde API'ye sorulur. Daha önce
   * panel yazılarının kendi adresi hiç yoktu — liste sayfasında bir kutu
   * olarak açılıyorlardı, yani paylaşılamıyor ve indekslenemiyorlardı.
   */
  const [panelPost, setPanelPost] = useState<PanelPost | null>(null);
  const [panelChecked, setPanelChecked] = useState(false);

  useEffect(() => {
    if (post || !slug || slug === '*') {
      setPanelChecked(true);
      return;
    }

    let cancelled = false;
    setPanelChecked(false);
    void fetchPanelPost(slug).then((found) => {
      if (cancelled) return;
      setPanelPost(found);
      setPanelChecked(true);
    });

    return () => {
      cancelled = true;
    };
  }, [post, slug]);

  useEffect(() => {
    if (!post) {
      return;
    }

    const seoMeta = getPostSeoMeta(post);
    const resolvedUrl = seoMeta.url ?? getCurrentPageUrl(location.pathname);
    const previousTitle = document.title;
    const previousLang = document.documentElement.lang;

    const metaDefinitions = [
      { attribute: 'name' as const, key: 'description', value: seoMeta.description },
      { attribute: 'name' as const, key: 'keywords', value: seoMeta.keywords },
      { attribute: 'property' as const, key: 'og:url', value: resolvedUrl },
      { attribute: 'property' as const, key: 'og:site_name', value: seoMeta.siteName },
      { attribute: 'property' as const, key: 'og:title', value: seoMeta.ogTitle },
      {
        attribute: 'property' as const,
        key: 'og:description',
        value: seoMeta.ogDescription,
      },
      { attribute: 'property' as const, key: 'og:image', value: seoMeta.ogImage },
      {
        attribute: 'property' as const,
        key: 'og:image:alt',
        value: seoMeta.ogImageAlt,
      },
      { attribute: 'property' as const, key: 'og:type', value: seoMeta.ogType },
      {
        attribute: 'property' as const,
        key: 'article:published_time',
        value: seoMeta.publishedTime,
      },
      { attribute: 'name' as const, key: 'twitter:card', value: seoMeta.twitterCard },
      { attribute: 'name' as const, key: 'twitter:site', value: seoMeta.twitterSite },
      {
        attribute: 'name' as const,
        key: 'twitter:creator',
        value: seoMeta.twitterCreator,
      },
      {
        attribute: 'name' as const,
        key: 'twitter:title',
        value: seoMeta.twitterTitle,
      },
      {
        attribute: 'name' as const,
        key: 'twitter:description',
        value: seoMeta.twitterDescription,
      },
      {
        attribute: 'name' as const,
        key: 'twitter:image',
        value: seoMeta.twitterImage,
      },
      {
        attribute: 'name' as const,
        key: 'twitter:image:alt',
        value: seoMeta.twitterImageAlt,
      },
    ];

    const previousValues = metaDefinitions.map(({ attribute, key, value }) => {
      if (!value) {
        return null;
      }

      const tag = ensureMetaTag(attribute, key);
      const previousContent = tag.content;
      tag.content = value;
      return { tag, previousContent };
    });

    document.title = seoMeta.title;
    if (seoMeta.lang) {
      document.documentElement.lang = seoMeta.lang;
    }

    const articleTagEntries = (seoMeta.tags ?? []).map((tag) => {
      const metaTag = document.createElement('meta');
      metaTag.setAttribute('property', 'article:tag');
      metaTag.content = tag;
      document.head.appendChild(metaTag);
      return metaTag;
    });

    return () => {
      document.title = previousTitle;
      document.documentElement.lang = previousLang;
      articleTagEntries.forEach((tag) => tag.remove());
      previousValues.forEach((entry) => {
        if (!entry) {
          return;
        }
        entry.tag.content = entry.previousContent;
      });
    };
  }, [post, location.pathname]);

  if (slug === '*') {
    return <Navigate to="/blog/" replace />;
  }

  if (!post && !panelChecked) {
    return (
      <main className="min-h-screen bg-[#05010a] flex items-center justify-center">
        <div className="h-8 w-8 rounded-full border-2 border-purple-500 border-t-transparent animate-spin" />
      </main>
    );
  }

  if (!post && panelPost) {
    return (
      <BlogArticleLayout title={panelPost.title} description={panelPost.excerpt}>
        <MarkdownArticle markdown={panelPost.content ?? ''} />
        <RelatedPosts posts={[]} />
      </BlogArticleLayout>
    );
  }

  if (!post) {
    // Türkçe bir sitede İngilizce 404 duruyordu; sayfa artık blogun
    // görsel diliyle aynı ve okuyucuyu yazı listesine geri gönderiyor.
    return (
      <main className="min-h-screen bg-[#05010a] text-[#ece6ff] flex items-center justify-center px-6 py-24">
        <div className="max-w-lg space-y-5 text-center">
          <p className="text-7xl font-bold text-purple-500/40">404</p>
          <h1 className="text-3xl font-bold text-white">Yazı bulunamadı</h1>
          <p className="text-lg leading-8 text-[#b9a9d6]">
            Aradığınız yazı kaldırılmış ya da adresi değişmiş olabilir.
          </p>
          <Link
            to="/blog"
            className="inline-flex text-sm font-semibold text-purple-300 underline underline-offset-4 hover:text-pink-300"
          >
            &larr; Tüm yazılara dön
          </Link>
        </div>
      </main>
    );
  }

  return (
    <BlogArticleLayout
      title={post.title}
      description={post.description}
      coverImage={`/blog-covers/${post.slug}.webp`}
      coverAlt={post.title}
    >
      <TableOfContents entries={getHeadings(post.markdown)} />
      <MarkdownArticle markdown={post.markdown} />
      {/*
        Paylaşım adresini `location.href` yerine kanonik adresten kuruyoruz:
        sunucuda basılırken `window` yok, ayrıca sorgu parametreli bir
        adres paylaşıldığında kırık bağlantı çıkıyordu.
      */}
      <ShareButtons
        url={`${SITE_URL}/blog/${post.slug}/`}
        title={post.title}
        className="mt-12 border-t border-white/5 pt-8"
      />
      <PostNavigation {...getAdjacentEntries(post.slug)} />
      <RelatedPosts posts={getRelatedEntries(post.slug)} />
    </BlogArticleLayout>
  );
};

export default BlogPostPage;
