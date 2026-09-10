import { useState } from 'react';

interface StoreBadgesProps {
  appStoreUrl?: string;
  googlePlayUrl?: string;
}

interface Store {
  key: string;
  href: string;
  /** Resmî rozet dosyası — public/store-badges/ altına konur. */
  badge: string;
  name: string;
  caption: string;
  alt: string;
}

/**
 * Uygulama mağazası bağlantıları.
 *
 * Apple ve Google'ın rozetleri onların markalarıdır ve yalnızca kendi
 * yayımladıkları dosyalar kullanılabilir; taklit edilmemeleri gerekir.
 * Bu yüzden bileşen resmî rozet dosyasını `public/store-badges/` altından
 * yükler. Dosya henüz eklenmemişse marka işareti içermeyen sade bir metin
 * düğmesine düşer — böylece bağlantı ilk günden çalışır, rozetler
 * eklendiğinde kendiliğinden görünür.
 *
 * Resmî dosyalar:
 *   App Store    — Apple Marketing Resources ("Download on the App Store")
 *   Google Play  — Google Play Badge Generator ("Google Play'den alın")
 * İndirilen dosyalar şu adlarla konur:
 *   public/store-badges/app-store.svg
 *   public/store-badges/google-play.svg
 */
export default function StoreBadges({ appStoreUrl, googlePlayUrl }: StoreBadgesProps) {
  const [failed, setFailed] = useState<Record<string, boolean>>({});

  const stores: Store[] = [
    appStoreUrl?.trim()
      ? {
          key: 'ios',
          href: appStoreUrl.trim(),
          badge: '/store-badges/app-store.svg',
          name: 'App Store',
          caption: 'İndir',
          alt: "App Store'dan indirin",
        }
      : null,
    googlePlayUrl?.trim()
      ? {
          key: 'android',
          href: googlePlayUrl.trim(),
          badge: '/store-badges/google-play.svg',
          name: 'Google Play',
          caption: 'İndir',
          alt: "Google Play'den indirin",
        }
      : null,
  ].filter(Boolean) as Store[];

  if (stores.length === 0) return null;

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      {stores.map((store) => (
        <a
          key={store.key}
          href={store.href}
          target="_blank"
          rel="noreferrer"
          aria-label={store.alt}
          className="inline-flex"
        >
          {failed[store.key] ? (
            <span className="inline-flex flex-col rounded-lg border border-white/15 bg-white/[0.04] px-4 py-2 transition-colors hover:border-purple-500/40">
              <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                {store.caption}
              </span>
              <span className="text-sm font-semibold text-foreground">{store.name}</span>
            </span>
          ) : (
            <img
              src={store.badge}
              alt={store.alt}
              width={140}
              height={42}
              loading="lazy"
              decoding="async"
              className="h-[42px] w-auto"
              onError={() => setFailed((prev) => ({ ...prev, [store.key]: true }))}
            />
          )}
        </a>
      ))}
    </div>
  );
}
