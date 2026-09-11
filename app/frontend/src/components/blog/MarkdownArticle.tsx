import Markdown from 'markdown-to-jsx';
import type { ReactNode } from 'react';

type MarkdownArticleProps = {
  markdown: string;
};

/**
 * Başlık metninden kalıcı bir id üretir.
 *
 * Türkçe karakterler ASCII karşılıklarına çevrilir; böylece bağlantılar
 * `#1-arama-motoru-nasil-calisir` gibi okunur ve URL'de bozulmaz kalır.
 * Aynı fonksiyon hem burada hem `getHeadings` içinde kullanıldığı için
 * içindekiler ile başlıklar her zaman eşleşir.
 */
export function slugifyHeading(text: string): string {
  const map: Record<string, string> = {
    ç: 'c', Ç: 'c', ğ: 'g', Ğ: 'g', ı: 'i', İ: 'i',
    ö: 'o', Ö: 'o', ş: 's', Ş: 's', ü: 'u', Ü: 'u',
  };

  return text
    .trim()
    .replace(/[çÇğĞıİöÖşŞüÜ]/g, (char) => map[char] ?? char)
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

/** Markdown gövdesindeki H2 başlıklarını sırayla döndürür. */
export function getHeadings(markdown: string) {
  const headings: { id: string; text: string }[] = [];
  const seen = new Map<string, number>();

  for (const match of markdown.matchAll(/^##\s+(.+?)\s*$/gm)) {
    const text = match[1].replace(/[*_`]/g, '').trim();
    const base = slugifyHeading(text);
    if (!base) continue;

    // Aynı başlık iki kez geçerse id'ler çakışmasın.
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    headings.push({ id: count === 0 ? base : `${base}-${count + 1}`, text });
  }

  return headings;
}

/** Başlık düğümünün düz metnini çıkarır. */
function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (typeof node === 'object' && 'props' in node) {
    return textOf((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return '';
}

function Heading({ children }: { children?: ReactNode }) {
  const text = textOf(children);
  return <h2 id={slugifyHeading(text)}>{children}</h2>;
}

/**
 * Tablo sarmalayıcı.
 *
 * Markdown tabloları telefonda sayfanın tamamını yana kaydırılır hâle
 * getiriyordu: 360 piksellik ekranda tablo 460 piksele çıkıyor ve gövde
 * onunla birlikte kayıyordu. Tablo artık kendi kaydırma kabında;
 * sayfa sabit kalıyor, yalnızca tablo kayıyor.
 *
 * `tabIndex` ve `role`: klavyeyle de kaydırılabilmesi için.
 */
function Table({ children, ...props }: { children?: ReactNode }) {
  return (
    <div className="not-prose my-8 overflow-x-auto rounded-xl border border-white/10">
      <table
        {...props}
        className="w-full min-w-[32rem] border-collapse text-left text-sm text-[#c4b6de]"
      >
        {children}
      </table>
    </div>
  );
}

const MarkdownArticle = ({ markdown }: MarkdownArticleProps) => (
  <div className="prose prose-invert prose-lg max-w-none prose-headings:text-white prose-h1:mt-0 prose-h1:text-4xl prose-h1:leading-tight prose-h2:mt-12 prose-h2:border-t prose-h2:border-white/10 prose-h2:pt-8 prose-h2:text-3xl prose-h2:leading-snug prose-h2:scroll-mt-24 prose-h3:mt-10 prose-h3:text-2xl prose-h3:leading-snug prose-p:text-[1.06rem] prose-p:leading-8 prose-p:text-[#c4b6de] prose-li:leading-8 prose-li:text-[#c4b6de] prose-strong:text-white prose-code:rounded prose-code:bg-purple-500/15 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[0.9em] prose-code:font-medium prose-code:text-purple-200 prose-pre:rounded-2xl prose-pre:bg-[#120727] prose-pre:p-5 prose-pre:text-[#ece6ff] prose-a:text-purple-300 prose-a:decoration-purple-500/50 prose-a:underline-offset-4 hover:prose-a:text-pink-300 prose-blockquote:border-l-purple-500 prose-blockquote:text-[#b9a9d6]">
    <Markdown
      options={{
        forceBlock: true,
        overrides: {
          // Başlıklara id verilir: içindekiler ve derin bağlantı için gerekli.
          h2: { component: Heading },
          a: {
            props: {
              className: 'font-medium',
            },
          },
          pre: {
            props: {
              className: 'overflow-x-auto',
            },
          },
          table: { component: Table },
          th: {
            props: {
              className:
                'border-b border-white/10 bg-white/[0.04] px-4 py-3 font-semibold text-white',
            },
          },
          td: {
            props: {
              className: 'border-b border-white/5 px-4 py-3 align-top leading-7',
            },
          },
        },
      }}
    >
      {markdown}
    </Markdown>
  </div>
);

export default MarkdownArticle;
