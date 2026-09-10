/**
 * Yazı adresini üretir.
 *
 * Ayrı bir dosyada duruyor: liste sayfası bunu kullanırken `lib/blog.ts`i
 * (dolayısıyla 61 makalenin gövdesini) içeri almak zorunda kalmasın.
 */
export function getBlogRoute(slug: string): string {
  return `/blog/${slug}/`.replace(/\/+/g, '/');
}
