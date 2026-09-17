import { useTranslation } from 'react-i18next';
import { useSiteSettings } from '@/lib/siteSettings';

/**
 * Marka künyesi: işaret + iki satırlık yazı.
 *
 * İşaret üç düğüm ve aralarındaki bağlantılardan oluşuyor — bir dağıtım
 * hattının (pipeline) soyutlaması. Renkleri sabit değil, temanın CSS
 * değişkenlerinden geliyor: `--primary` dış düğümler, `--marka-ikinci` orta
 * düğüm, `--border` bağlantı çizgileri. Böylece aynı bileşen mor temada mor,
 * yeşil temada yeşil çiziliyor; renk denemesi için ayrı bir logo dosyası
 * tutmak gerekmiyor.
 *
 * Panelden `brand_logo` ayarlanmışsa o görsel kullanılır; işaret yalnızca
 * varsayılan durumda çizilir.
 */
export default function MarkaLogosu({
  yazi = true,
  boyut = 34,
  className = '',
}: {
  /** Künye yazısı gösterilsin mi? Dar alanlarda kapatılabilir. */
  yazi?: boolean;
  /** İşaretin kenar uzunluğu (px). */
  boyut?: number;
  className?: string;
}) {
  const { t } = useTranslation();
  const { settings } = useSiteSettings();

  /*
   * Panelde `brand_logo` eski varsayilan gorseli gosteriyor olabilir; o durumda
   * yeni isareti ciziyoruz. Yalnizca gercekten baska bir dosya secilmisse o
   * gorsel kullaniliyor -- boylece panelden ozel logo koymus biri kaybetmiyor.
   */
  const ESKI_VARSAYILANLAR = [
    '/assets/logo-mark-144.webp',
    '/assets/logo-mark.webp',
    '/assets/logo.webp',
  ];
  const ayarliLogo = (settings.brand_logo || '').trim();
  const ozelLogo = ayarliLogo && !ESKI_VARSAYILANLAR.includes(ayarliLogo) ? ayarliLogo : '';

  return (
    <span className={`flex items-center gap-3 ${className}`}>
      {ozelLogo ? (
        <img
          src={ozelLogo}
          alt={t('ui.logoAlt')}
          width={boyut}
          height={boyut}
          decoding="async"
          className="object-contain transition-transform group-hover:scale-105"
          style={{ width: boyut, height: boyut }}
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).style.display = 'none';
          }}
        />
      ) : (
        <svg
          width={boyut}
          height={boyut}
          viewBox="0 0 32 32"
          fill="none"
          role="img"
          aria-label={t('ui.logoAlt')}
          className="flex-none transition-transform group-hover:scale-105"
        >
          <path
            d="M9 16h3.6M19.4 16H23"
            stroke="hsl(var(--border))"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <circle cx="6" cy="16" r="3.4" fill="hsl(var(--primary))" />
          <circle cx="16" cy="16" r="3.4" fill="hsl(var(--marka-ikinci))" />
          <circle cx="26" cy="16" r="3.4" fill="hsl(var(--primary))" />
        </svg>
      )}

      {yazi && (
        <span className="leading-none">
          <span className="block font-bold tracking-tight text-[15px] text-foreground">
            {t('ui.brandName')}
          </span>
          <span className="mt-1 block text-[9.5px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            {t('ui.brandTagline')}
          </span>
        </span>
      )}
    </span>
  );
}
