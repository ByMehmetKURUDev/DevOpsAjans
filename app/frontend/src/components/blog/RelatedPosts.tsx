import { Link } from 'react-router-dom';
import { getBlogRoute } from '@/lib/blogRoute';
import type { BlogIndexEntry } from '@/lib/blogIndex';

/**
 * İlgili yazılar ve hizmet sayfasına çağrı.
 *
 * 61 yazı birbirine hiç link vermiyordu — okuyucu yazıyı bitiriyor ve
 * yapacak bir şey bulamıyordu. Bu blok hem konu kümesi içinde gezinme
 * sağlıyor hem de yazının sonunda bir sonraki adımı gösteriyor.
 */
export default function RelatedPosts({ posts }: { posts: BlogIndexEntry[] }) {
  return (
    <aside className="mt-16 border-t border-white/10 pt-10">
      {posts.length > 0 ? (
        <>
          <h2 className="text-xl font-semibold text-white">İlgili yazılar</h2>
          <ul className="mt-6 grid gap-4 sm:grid-cols-2">
            {posts.map((post) => (
              <li
                key={post.slug}
                className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 transition-colors hover:border-purple-500/40"
              >
                {post.category ? (
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-purple-400">
                    {post.category}
                  </span>
                ) : null}
                <h3 className="mt-2 text-base font-semibold leading-snug text-white">
                  <Link className="hover:text-purple-300" to={getBlogRoute(post.slug)}>
                    {post.title}
                  </Link>
                </h3>
                <p className="mt-2 line-clamp-3 text-sm leading-6 text-[#b9a9d6]">
                  {post.description}
                </p>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <div className="mt-10 rounded-3xl border border-purple-500/25 bg-purple-500/[0.07] p-6 sm:p-8">
        <h2 className="text-xl font-semibold text-white">
          Bu konuyu kendi siteniz için konuşalım
        </h2>
        <p className="mt-3 max-w-2xl text-base leading-7 text-[#b9a9d6]">
          Yazıdakileri kendi sitenize uygulamak için nereden başlayacağınızı
          birlikte çıkaralım. Projenizi anlatın, 24 saat içinde dürüst bir
          değerlendirmeyle dönüş yapayım.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/contact"
            className="rounded-full bg-purple-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-purple-400"
          >
            İletişime geç
          </Link>
          <Link
            to="/services"
            className="rounded-full border border-white/15 px-5 py-2.5 text-sm font-semibold text-[#d7cbee] transition-colors hover:border-purple-500/40 hover:text-white"
          >
            Hizmetleri gör
          </Link>
        </div>
      </div>
    </aside>
  );
}
