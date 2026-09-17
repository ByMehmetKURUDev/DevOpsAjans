import { useState } from 'react';
import { Check, Link2, Share2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { SOCIAL_ICONS as BRAND } from '@/lib/brandIcons';

interface ShareButtonsProps {
  /** Paylaşılacak sayfanın tam adresi. Sunucuda basılırken de doğru olmalı. */
  url: string;
  title: string;
  className?: string;
}

const LINKEDIN_PATH =
  'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z';

const WHATSAPP_PATH =
  'M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.149-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884a9.82 9.82 0 0 1 6.988 2.896 9.83 9.83 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.82 11.82 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.88 11.88 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893A11.82 11.82 0 0 0 20.464 3.488';

/**
 * Yazı paylaşım butonları.
 *
 * Cihazın kendi paylaşım penceresi varsa (telefonlar) önce o kullanılıyor;
 * masaüstünde tek tek ağ bağlantıları gösteriliyor. Bağlantıyı kopyala her
 * yerde çalışıyor ve kopyalandığında iki saniyeliğine onay veriyor.
 */
export default function ShareButtons({ url, title, className = '' }: ShareButtonsProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const e = encodeURIComponent;
  const targets = [
    {
      label: 'X',
      path: BRAND.x.path,
      href: `https://twitter.com/intent/tweet?url=${e(url)}&text=${e(title)}`,
    },
    {
      label: 'LinkedIn',
      path: LINKEDIN_PATH,
      href: `https://www.linkedin.com/sharing/share-offsite/?url=${e(url)}`,
    },
    {
      label: 'Facebook',
      path: BRAND.facebook.path,
      href: `https://www.facebook.com/sharer/sharer.php?u=${e(url)}`,
    },
    {
      label: 'WhatsApp',
      path: WHATSAPP_PATH,
      href: `https://wa.me/?text=${e(`${title} ${url}`)}`,
    },
  ];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Pano izni yoksa sessizce geç: bağlantı zaten adres çubuğunda.
    }
  };

  const nativeShare = async () => {
    try {
      await navigator.share({ title, url });
    } catch {
      // Kullanıcı vazgeçti ya da tarayıcı desteklemiyor.
    }
  };

  const chip =
    'inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 text-sm text-[#b9a9d6] transition-colors hover:border-purple-500/40 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-400';

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <span className="me-1 inline-flex items-center gap-2 text-sm font-semibold text-[#9d8cbf]">
        <Share2 className="h-4 w-4" aria-hidden="true" />
        {t('ui.shareTitle')}
      </span>

      {targets.map((target) => (
        <a
          key={target.label}
          href={target.href}
          target="_blank"
          rel="noopener noreferrer"
          className={chip}
          aria-label={t('ui.shareOn', { network: target.label })}
          title={target.label}
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
            <path d={target.path} />
          </svg>
        </a>
      ))}

      <button type="button" onClick={copy} className={chip} aria-live="polite">
        {copied ? (
          <>
            <Check className="h-4 w-4 text-emerald-400" aria-hidden="true" />
            {t('ui.linkCopied')}
          </>
        ) : (
          <>
            <Link2 className="h-4 w-4" aria-hidden="true" />
            {t('ui.copyLink')}
          </>
        )}
      </button>

      {typeof navigator !== 'undefined' && 'share' in navigator ? (
        <button type="button" onClick={nativeShare} className={`${chip} sm:hidden`}>
          <Share2 className="h-4 w-4" aria-hidden="true" />
          {t('ui.shareOther')}
        </button>
      ) : null}
    </div>
  );
}
