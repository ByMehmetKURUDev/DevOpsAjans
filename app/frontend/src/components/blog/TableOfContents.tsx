/**
 * Yazı içindekiler tablosu.
 *
 * Markdown başlıklarına id verilmediği için ne içindekiler ne de derin
 * bağlantı mümkündü. `MarkdownArticle` artık her H2'ye kalıcı bir id
 * basıyor, bu bileşen de onlara bağlanıyor.
 */
export interface TocEntry {
  id: string;
  text: string;
}

export default function TableOfContents({ entries }: { entries: TocEntry[] }) {
  // Üç başlığın altında içindekiler yer kaplamaktan başka bir işe yaramıyor.
  if (entries.length < 3) return null;

  return (
    <nav
      aria-label="İçindekiler"
      className="mt-10 rounded-2xl border border-white/10 bg-white/[0.03] p-6"
    >
      <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-purple-400">
        İçindekiler
      </h2>
      <ol className="mt-4 space-y-2">
        {entries.map((entry, index) => (
          <li key={entry.id} className="flex gap-3 text-[0.95rem] leading-7">
            <span className="tabular-nums text-[#7d6ea3]">
              {String(index + 1).padStart(2, '0')}
            </span>
            <a
              className="text-[#c4b6de] underline-offset-4 transition-colors hover:text-purple-300 hover:underline"
              href={`#${entry.id}`}
            >
              {entry.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
