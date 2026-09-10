import { Link } from 'react-router-dom';
import { getBlogRoute } from '@/lib/blogRoute';
import type { BlogIndexEntry } from '@/lib/blogIndex';

interface PostNavigationProps {
  older?: BlogIndexEntry;
  newer?: BlogIndexEntry;
}

/**
 * Yazı sonu gezinmesi: önceki ve sonraki yazı.
 *
 * Okuyucu yazıyı bitirdiğinde tek çıkış yolu tarayıcının geri tuşuydu.
 * Yayın sırasına göre komşu yazılar hem okumayı sürdürüyor hem de her
 * yazıya iki iç link daha kazandırıyor.
 */
export default function PostNavigation({ older, newer }: PostNavigationProps) {
  if (!older && !newer) return null;

  return (
    <nav
      aria-label="Yazılar arasında gezinme"
      className="mt-12 grid gap-4 border-t border-white/10 pt-8 sm:grid-cols-2"
    >
      {older ? (
        <Link
          to={getBlogRoute(older.slug)}
          rel="prev"
          className="group rounded-2xl border border-white/10 bg-white/[0.03] p-5 transition-colors hover:border-purple-500/40"
        >
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[#9d8cbf]">
            &larr; Önceki yazı
          </span>
          <span className="mt-2 block text-base font-semibold leading-snug text-white group-hover:text-purple-300">
            {older.title}
          </span>
        </Link>
      ) : (
        <span aria-hidden="true" className="hidden sm:block" />
      )}

      {newer ? (
        <Link
          to={getBlogRoute(newer.slug)}
          rel="next"
          className="group rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-right transition-colors hover:border-purple-500/40 sm:text-right"
        >
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[#9d8cbf]">
            Sonraki yazı &rarr;
          </span>
          <span className="mt-2 block text-base font-semibold leading-snug text-white group-hover:text-purple-300">
            {newer.title}
          </span>
        </Link>
      ) : null}
    </nav>
  );
}
