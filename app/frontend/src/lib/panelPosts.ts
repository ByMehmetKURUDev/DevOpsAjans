import { useEffect, useState } from 'react';
import { client } from '@/lib/sdkClient';

/** Yönetim panelinden yayımlanan blog yazısı. */
export interface PanelPost {
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

/**
 * Panelden yayımlanan yazıları çeker.
 *
 * Bu yazılar build sırasında erişilemediği için prerender edilemiyor;
 * markdown yazıları statik HTML olarak gelir, bunlar sayfa yüklendikten
 * sonra aynı listeye eklenir. Backend'e ulaşılamazsa liste sessizce
 * markdown yazılarıyla sınırlı kalır — hata kullanıcıya gösterilmez,
 * çünkü sayfanın asıl içeriği zaten yerinde.
 */
export function usePanelPosts() {
  const [posts, setPosts] = useState<PanelPost[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    client.entities.blog_posts
      .query({ query: { published: true }, sort: '-created_at', limit: 50 })
      .then((res: { data?: { items?: PanelPost[] } }) => {
        if (cancelled) return;
        setPosts((res?.data?.items ?? []).filter((p) => p?.slug && p?.title));
      })
      .catch(() => {
        if (!cancelled) setPosts([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { panelPosts: posts, panelLoading: loading };
}

/**
 * Tek bir panel yazısını slug ile sorgular. `hata: true` = arka uca ulaşılamadı;
 * yazının olmadığı KESİN değil (bulunamadı sayfası `noindex` basmasın diye ayrı).
 */
export async function panelYazisiniSorgula(
  slug: string,
): Promise<{ yazi: PanelPost | null; hata: boolean }> {
  try {
    const res = (await client.entities.blog_posts.query({
      query: { slug, published: true },
      limit: 1,
    })) as { data?: { items?: PanelPost[] } };
    return { yazi: res?.data?.items?.[0] ?? null, hata: false };
  } catch {
    return { yazi: null, hata: true };
  }
}

/** Tek bir panel yazısını slug ile getirir (bulunamazsa ya da hata olursa null). */
export async function fetchPanelPost(slug: string): Promise<PanelPost | null> {
  return (await panelYazisiniSorgula(slug)).yazi;
}
