import { SOCIAL_ICONS as BRAND } from '@/lib/brandIcons';
import type { SettingsMap } from '@/lib/siteSettings';

/**
 * Sosyal ağların TEK kaynağı.
 *
 * Daha önce aynı liste hem `Layout.tsx` hem `Contact.tsx` içinde ayrı ayrı
 * duruyordu; ikisi birbirinden kopmuştu ve yalnızca iletişim sayfasındaki
 * bağlantılar çalışıyordu. Artık üç yer de (footer, Nasıl Çalışır, İletişim)
 * buradan besleniyor, adres panelden giriliyor.
 */
export interface SocialDef {
  /** Panelde saklanan ayar anahtarı. */
  key: string;
  label: string;
  /** 24x24 viewBox içindeki tek SVG yolu. */
  path: string;
}

/**
 * LinkedIn simple-icons'ta yok (marka kendi talebiyle kaldırıldı); projede
 * zaten bulunan yol korunuyor. Diğerleri `brandIcons.ts` üzerinden geliyor.
 */
const LINKEDIN_PATH =
  'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z';

export const SOCIAL_DEFS: SocialDef[] = [
  { key: 'social_facebook', label: 'Facebook', path: BRAND.facebook.path },
  { key: 'social_instagram', label: 'Instagram', path: BRAND.instagram.path },
  { key: 'social_twitter', label: 'X (Twitter)', path: BRAND.x.path },
  { key: 'social_linkedin', label: 'LinkedIn', path: LINKEDIN_PATH },
  { key: 'social_youtube', label: 'YouTube', path: BRAND.youtube.path },
  { key: 'social_github', label: 'GitHub', path: BRAND.github.path },
  { key: 'social_envato', label: 'Envato', path: BRAND.envato.path },
];

/** Panelde adresi girilmiş olanlar. Boş bırakılan ağ hiç gösterilmez. */
export function activeSocials(settings: SettingsMap): (SocialDef & { url: string })[] {
  return SOCIAL_DEFS.map((def) => ({ ...def, url: (settings[def.key] || '').trim() })).filter(
    (item) => item.url.length > 0,
  );
}
