import { useTranslation } from 'react-i18next';
import { DEFAULT_TOOL_ORDER, TOOL_ICONS } from '@/lib/brandIcons';
import { useSiteSettings } from '@/lib/siteSettings';

/**
 * Kullanılan Araçlar.
 *
 * Liste panelden (`tools_list`) virgülle ayrılmış slug'larla değiştirilebiliyor;
 * boşsa koddaki varsayılan sıra kullanılıyor. Tanınmayan bir slug sessizce
 * atlanıyor, böylece panelde yapılan yazım hatası bölümü kırmıyor.
 *
 * İkonlar markaların kendi yayımladığı işaretler (`scripts/generate-brand-icons.mjs`).
 * Tek renk gösteriliyorlar; üzerine gelince markanın kendi rengine dönüyorlar.
 */
export default function ToolsUsed({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const { settings } = useSiteSettings();

  const configured = (settings.tools_list || '')
    .split(',')
    .map((slug) => slug.trim().toLowerCase())
    .filter(Boolean);

  const slugs = (configured.length > 0 ? configured : DEFAULT_TOOL_ORDER).filter(
    (slug) => TOOL_ICONS[slug],
  );

  if (slugs.length === 0) return null;

  return (
    <section className={`py-20 border-t border-white/5 ${className}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-10 text-center">
          <p className="text-xs uppercase tracking-[0.3em] text-cyan-400 mb-4">
            {t('tools.sectionTag')}
          </p>
          <h2 className="text-3xl md:text-4xl font-bold">{t('tools.title')}</h2>
          <p className="mt-4 text-muted-foreground max-w-2xl mx-auto">{t('tools.desc')}</p>
        </div>

        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
          {slugs.map((slug) => {
            const icon = TOOL_ICONS[slug];
            return (
              <li key={slug}>
                <div
                  className="group flex h-full flex-col items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-4 transition-colors hover:border-purple-500/40"
                  title={icon.title}
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-7 w-7 text-[#b9a9d6] transition-colors group-hover:text-white"
                    fill="currentColor"
                    role="img"
                    aria-label={icon.title}
                  >
                    <path d={icon.path} />
                  </svg>
                  <span className="text-center text-[11px] leading-tight text-muted-foreground">
                    {icon.title}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
