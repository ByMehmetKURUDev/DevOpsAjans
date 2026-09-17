import { useTranslation } from 'react-i18next';

interface PaginationProps {
  page: number;
  pageCount: number;
  /** Verilen sayfanın adresini üretir; bağlantılar gerçek `href` taşısın diye. */
  hrefFor: (page: number) => string;
  onNavigate: (page: number) => void;
}

/**
 * Sayfa numaraları.
 *
 * Çok sayfada bütün numaraları basmak yerine baş, son ve aktif sayfanın
 * çevresi gösterilir; aradaki boşluklar üç nokta ile belirtilir.
 * Dönen dizide `null` değerler bu boşlukları temsil eder.
 */
function pageWindow(page: number, pageCount: number): (number | null)[] {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, i) => i + 1);
  }

  const items = new Set<number>([1, pageCount, page]);
  if (page - 1 > 1) items.add(page - 1);
  if (page + 1 < pageCount) items.add(page + 1);
  if (page <= 3) [2, 3, 4].forEach((p) => items.add(p));
  if (page >= pageCount - 2) [pageCount - 3, pageCount - 2, pageCount - 1].forEach((p) => items.add(p));

  const sorted = Array.from(items)
    .filter((p) => p >= 1 && p <= pageCount)
    .sort((a, b) => a - b);

  const result: (number | null)[] = [];
  sorted.forEach((value, index) => {
    if (index > 0 && value - sorted[index - 1] > 1) result.push(null);
    result.push(value);
  });
  return result;
}

const baseButton =
  'inline-flex h-10 min-w-10 items-center justify-center rounded-xl border px-3 text-sm font-semibold transition-colors';

const Pagination = ({ page, pageCount, hrefFor, onNavigate }: PaginationProps) => {
  const { t } = useTranslation();
  if (pageCount <= 1) return null;

  const go = (event: React.MouseEvent, target: number) => {
    // Ctrl/Cmd tıklaması ve orta tuş tarayıcıya bırakılır: bağlantı gerçek
    // bir adres taşıdığı için yeni sekmede açılabilmeli.
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onNavigate(target);
  };

  const items = pageWindow(page, pageCount);

  return (
    <nav className="mt-12 flex flex-wrap items-center justify-center gap-2" aria-label={t('ui.pagination')}>
      <a
        href={hrefFor(page - 1)}
        onClick={(e) => go(e, page - 1)}
        aria-disabled={page === 1}
        className={`${baseButton} ${
          page === 1
            ? 'pointer-events-none border-white/5 text-[#6b5f85]'
            : 'border-white/10 bg-white/[0.03] text-[#b9a9d6] hover:border-purple-500/40 hover:text-white'
        }`}
      >
        &larr; {t('ui.prevPage')}
      </a>

      {items.map((value, index) =>
        value === null ? (
          <span key={`bosluk-${index}`} className="px-2 text-[#6b5f85]" aria-hidden="true">
            &hellip;
          </span>
        ) : (
          <a
            key={value}
            href={hrefFor(value)}
            onClick={(e) => go(e, value)}
            aria-label={t('ui.goToPage', { page: value })}
            aria-current={value === page ? 'page' : undefined}
            className={`${baseButton} ${
              value === page
                ? 'border-purple-400 bg-purple-500/20 text-white'
                : 'border-white/10 bg-white/[0.03] text-[#b9a9d6] hover:border-purple-500/40 hover:text-white'
            }`}
          >
            {value}
          </a>
        ),
      )}

      <a
        href={hrefFor(page + 1)}
        onClick={(e) => go(e, page + 1)}
        aria-disabled={page === pageCount}
        className={`${baseButton} ${
          page === pageCount
            ? 'pointer-events-none border-white/5 text-[#6b5f85]'
            : 'border-white/10 bg-white/[0.03] text-[#b9a9d6] hover:border-purple-500/40 hover:text-white'
        }`}
      >
        {t('ui.nextPage')} &rarr;
      </a>
    </nav>
  );
};

export default Pagination;
