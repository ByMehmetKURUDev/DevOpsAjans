import { useTranslation } from 'react-i18next';
import { useSiteSettings } from '@/lib/siteSettings';

/**
 * Marka künyesi.
 *
 * Tasarım, kullanıcının verdiği prototipten birebir alındı: yuvarlatılmış
 * kare içinde `</>` işareti, sağ üst köşede canlılık noktası, yanında iki
 * satırlık künye ("By Mehmet KURU Dev" / "Full-stack & AI Systems").
 *
 * Renkleri bilerek sabit — hem vurgu (#00DC82) hem kutunun yeşil-mor degrade
 * zemini. Logo bir marka işaretidir, tema rengine göre değişmemeli; bu sayede
 * mor ve yeşil dalda birebir aynı çiziliyor.
 *
 * Panelden `brand_logo` ile başka bir görsel seçilmişse o kullanılır; eski
 * varsayılan dosyalar bu işaretle değiştirilir.
 */

const VURGU = '#00DC82';

const ESKI_VARSAYILANLAR = [
  '/assets/logo-mark-144.webp',
  '/assets/logo-mark.webp',
  '/assets/logo.webp',
];

export default function MarkaLogosu({
  yazi = true,
  className = '',
}: {
  /** Künye yazısı gösterilsin mi? Dar alanlarda kapatılabilir. */
  yazi?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const { settings } = useSiteSettings();

  const ayarliLogo = (settings.brand_logo || '').trim();
  const ozelLogo = ayarliLogo && !ESKI_VARSAYILANLAR.includes(ayarliLogo) ? ayarliLogo : '';

  return (
    <span className={`flex items-center gap-3 ${className}`}>
      {ozelLogo ? (
        <img
          src={ozelLogo}
          alt={t('ui.logoAlt')}
          width={40}
          height={40}
          decoding="async"
          className="h-10 w-10 object-contain transition-transform group-hover:scale-105"
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).style.display = 'none';
          }}
        />
      ) : (
        <span
          className="relative flex h-10 w-10 flex-none items-center justify-center rounded-xl border transition-colors"
          style={{
            borderColor: `${VURGU}4d`,
            backgroundImage:
              'linear-gradient(to bottom right, rgba(52, 211, 153, .25), rgba(147, 51, 234, .35))',
          }}
          role="img"
          aria-label={t('ui.logoAlt')}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke={VURGU}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m18 16 4-4-4-4" />
            <path d="m6 8-4 4 4 4" />
            <path d="m14.5 4-5 16" />
          </svg>
          {/* Canlilik noktasi: disaridaki halka nabiz gibi atiyor, icteki sabit.
              Hareketi azaltilmis modda halka gizleniyor. */}
          <span
            className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full opacity-75 motion-safe:animate-ping motion-reduce:hidden"
            style={{ backgroundColor: VURGU }}
            aria-hidden="true"
          />
          <span
            className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: VURGU }}
            aria-hidden="true"
          />
        </span>
      )}

      {yazi && (
        <span className="flex flex-col leading-none">
          <span className="text-base font-extrabold tracking-tight text-white sm:text-lg">
            {t('ui.brandPrefix')}
            <span style={{ color: VURGU }}>{t('ui.brandHighlight')}</span> {t('ui.brandSuffix')}
          </span>
          <span className="mt-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {t('ui.brandTagline')}
          </span>
        </span>
      )}
    </span>
  );
}
