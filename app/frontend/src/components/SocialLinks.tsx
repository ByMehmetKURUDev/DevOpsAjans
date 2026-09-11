import { useTranslation } from 'react-i18next';
import { useSiteSettings } from '@/lib/siteSettings';
import { activeSocials } from '@/lib/socialLinks';

type Variant = 'icon' | 'pill';

interface SocialLinksProps {
  /** `icon` yalnızca simge (footer), `pill` simge + ad (Nasıl Çalışır, İletişim). */
  variant?: Variant;
  className?: string;
}

/**
 * Panelde adresi girilmiş sosyal ağları listeler.
 *
 * Tek kontrol noktası: footer, Nasıl Çalışır ve İletişim aynı bileşeni
 * kullanıyor, hepsi `site_settings` içindeki `social_*` anahtarlarından
 * besleniyor. Adresi boş olan ağ hiçbir yerde görünmüyor.
 *
 * `flex-wrap` zorunlu: yedi ağ birden doluyken dar ekranda yatayda taşıyordu.
 */
export default function SocialLinks({ variant = 'icon', className = '' }: SocialLinksProps) {
  const { settings } = useSiteSettings();
  const { t } = useTranslation();
  const items = activeSocials(settings);

  if (items.length === 0) return null;

  const base =
    variant === 'pill'
      ? 'inline-flex items-center gap-2 px-4 py-2 rounded-full glass text-sm hover:border-purple-500/40 hover:text-white transition-colors'
      : 'inline-flex h-10 w-10 items-center justify-center rounded-xl glass text-muted-foreground hover:text-white hover:border-purple-500/40 transition-colors';

  return (
    <ul className={`flex flex-wrap items-center gap-3 ${className}`} aria-label={t('ui.socialLinks')}>
      {items.map((item) => (
        <li key={item.key}>
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer me"
            className={base}
            aria-label={item.label}
            title={item.label}
          >
            <svg
              viewBox="0 0 24 24"
              className={variant === 'pill' ? 'h-4 w-4' : 'h-[18px] w-[18px]'}
              fill="currentColor"
              aria-hidden="true"
            >
              <path d={item.path} />
            </svg>
            {variant === 'pill' ? <span>{item.label}</span> : null}
          </a>
        </li>
      ))}
    </ul>
  );
}
