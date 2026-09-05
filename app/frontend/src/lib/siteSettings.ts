import { useCallback, useEffect, useMemo, useState } from 'react';
import { createClient } from '@metagptx/web-sdk';
import { useTranslation } from 'react-i18next';
import { LANGUAGE_CODES } from '@/i18n';

const client = createClient();

export type SettingsMap = Record<string, string>;

export interface SettingRow {
  id: number | string;
  setting_key: string;
  setting_value: string;
  group_name?: string;
  label?: string;
}

/** Yedek değerler — backend erişilemezse site yine tutarlı görünür. */
export const DEFAULT_SETTINGS: SettingsMap = {
  brand_logo: '/assets/logo-new.jpg',
  hero_title: 'Dijital Fikirlerinizi Ölçeklenebilir Ürünlere Dönüştürüyoruz',
  hero_subtitle:
    'Website, e-ticaret, SaaS ve mobil uygulama geliştirme; uçtan uca tasarım, kod ve büyüme desteği.',
  hero_cta: 'Ücretsiz Keşif Görüşmesi',
  contact_email: 'by@mehmetkuru.dev',
  contact_phone: '0541 296 58 78',
  contact_address: 'Sultan Selim Mah. Kağıthane / İstanbul',
  whatsapp_number: '905412965878',
  social_facebook: '',
  social_instagram: '',
  social_twitter: '',
  social_linkedin: '',
  social_youtube: '',
  social_github: '',
  price_starter: '100',
  price_business: '300',
  price_ecommerce: '500',
  price_saas: '700',
  price_devops: '1200',
  ga4_measurement_id: 'G-297VMX9Z6X',
  seo_meta_title: 'Mehmet KURU Dev',
  seo_meta_description: 'Web, e-ticaret, SaaS ve mobil uygulama geliştirme ajansı.',
  admin_emails: 'by@mehmetkuru.dev',
};

/**
 * Dil bazlı saklanan ayar anahtarları.
 * Örnek: `hero_title` temel (varsayılan) değer, `hero_title__ar` Arapça karşılığı.
 */
export const TRANSLATABLE_KEYS = [
  'hero_title',
  'hero_subtitle',
  'hero_cta',
  'contact_address',
  'seo_meta_title',
  'seo_meta_description',
] as const;

export type TranslatableKey = (typeof TRANSLATABLE_KEYS)[number];

export function isTranslatableKey(key: string): boolean {
  return (TRANSLATABLE_KEYS as readonly string[]).includes(key);
}

/** Dil bazlı ayar anahtarını üretir. */
export function localizedSettingKey(key: string, lang: string): string {
  return `${key}__${lang}`;
}

/** Aktif dile göre ayar değerini çözer; dil karşılığı boşsa temel değere düşer. */
export function resolveSetting(settings: SettingsMap, key: string, lang?: string): string {
  if (lang && isTranslatableKey(key)) {
    const localized = settings[localizedSettingKey(key, lang)];
    if (localized && localized.trim()) return localized;
  }
  return settings[key] ?? '';
}

/** Tüm çevrilebilir anahtarları aktif dile göre çözülmüş bir haritaya uygular. */
export function localizeSettings(settings: SettingsMap, lang?: string): SettingsMap {
  if (!lang) return settings;
  const resolved: SettingsMap = { ...settings };
  TRANSLATABLE_KEYS.forEach((key) => {
    resolved[key] = resolveSetting(settings, key, lang);
  });
  return resolved;
}

/** Admin panelindeki "Site Ayarları" sekmesinin form düzeni. */
export const SETTING_GROUPS: {
  group: string;
  title: string;
  description: string;
  fields: { key: string; label: string; multiline?: boolean; translatable?: boolean }[];
}[] = [
  {
    group: 'brand',
    title: 'settingsForm.brandTitle',
    description: 'settingsForm.brandDesc',
    fields: [{ key: 'brand_logo', label: 'settingsForm.fBrandLogo' }],
  },
  {
    group: 'hero',
    title: 'settingsForm.heroTitle',
    description: 'settingsForm.heroDesc',
    fields: [
      {
        key: 'hero_title',
        label: 'settingsForm.fHeroTitle',
        multiline: true,
        translatable: true,
      },
      {
        key: 'hero_subtitle',
        label: 'settingsForm.fHeroSubtitle',
        multiline: true,
        translatable: true,
      },
      { key: 'hero_cta', label: 'settingsForm.fHeroCta', translatable: true },
    ],
  },
  {
    group: 'contact',
    title: 'settingsForm.contactTitle',
    description: 'settingsForm.contactDesc',
    fields: [
      { key: 'contact_email', label: 'settingsForm.fEmail' },
      { key: 'contact_phone', label: 'settingsForm.fPhone' },
      { key: 'contact_address', label: 'settingsForm.fAddress', translatable: true },
      { key: 'whatsapp_number', label: 'settingsForm.fWhatsapp' },
    ],
  },
  {
    group: 'social',
    title: 'settingsForm.socialTitle',
    description: 'settingsForm.socialDesc',
    fields: [
      { key: 'social_facebook', label: 'settingsForm.fFacebook' },
      { key: 'social_instagram', label: 'settingsForm.fInstagram' },
      { key: 'social_twitter', label: 'settingsForm.fTwitter' },
      { key: 'social_linkedin', label: 'settingsForm.fLinkedin' },
      { key: 'social_youtube', label: 'settingsForm.fYoutube' },
      { key: 'social_github', label: 'settingsForm.fGithub' },
    ],
  },
  {
    group: 'pricing',
    title: 'settingsForm.pricingTitle',
    description: 'settingsForm.pricingDesc',
    fields: [
      { key: 'price_starter', label: 'settingsForm.fStarter' },
      { key: 'price_business', label: 'settingsForm.fBusiness' },
      { key: 'price_ecommerce', label: 'settingsForm.fEcommerce' },
      { key: 'price_saas', label: 'settingsForm.fSaas' },
      { key: 'price_devops', label: 'settingsForm.fDevops' },
    ],
  },
  {
    group: 'analytics',
    title: 'settingsForm.analyticsTitle',
    description: 'settingsForm.analyticsDesc',
    fields: [
      { key: 'ga4_measurement_id', label: 'settingsForm.fGa4' },
      { key: 'seo_meta_title', label: 'settingsForm.fSeoTitle', translatable: true },
      {
        key: 'seo_meta_description',
        label: 'settingsForm.fSeoDesc',
        multiline: true,
        translatable: true,
      },
    ],
  },
  {
    group: 'access',
    title: 'settingsForm.accessTitle',
    description: 'settingsForm.accessDesc',
    fields: [{ key: 'admin_emails', label: 'settingsForm.fAdminEmails' }],
  },
];

const CACHE_KEY = 'mk_site_settings_v2';

let memoryCache: SettingsMap | null = null;
let inFlight: Promise<SettingsMap> | null = null;

function readCache(): SettingsMap | null {
  if (memoryCache) return memoryCache;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SettingsMap;
    memoryCache = { ...DEFAULT_SETTINGS, ...parsed };
    return memoryCache;
  } catch {
    return null;
  }
}

function writeCache(map: SettingsMap) {
  memoryCache = map;
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(map));
  } catch {
    /* storage kullanılamıyorsa sessizce geç */
  }
}

/** Tüm ayarları backend'den okur, key/value haritasına çevirir. */
export async function fetchSiteSettings(force = false): Promise<SettingsMap> {
  if (!force) {
    const cached = readCache();
    if (cached) return cached;
    if (inFlight) return inFlight;
  }

  const request = (async () => {
    try {
      const res = await client.entities.site_settings.query({ limit: 500 });
      const items = (res?.data?.items ?? []) as SettingRow[];
      const map: SettingsMap = { ...DEFAULT_SETTINGS };
      items.forEach((row) => {
        if (row?.setting_key) map[row.setting_key] = row.setting_value ?? '';
      });
      writeCache(map);
      return map;
    } catch {
      return readCache() ?? { ...DEFAULT_SETTINGS };
    } finally {
      inFlight = null;
    }
  })();

  inFlight = request;
  return request;
}

/** Ham satırları döndürür — admin panelinde güncelleme için id gerekir. */
export async function fetchSettingRows(): Promise<SettingRow[]> {
  const res = await client.entities.site_settings.query({ limit: 500 });
  return (res?.data?.items ?? []) as SettingRow[];
}

/** Ayarı günceller; kayıt yoksa oluşturur. */
export async function saveSiteSetting(
  rows: SettingRow[],
  key: string,
  value: string,
  groupName?: string,
  label?: string
): Promise<void> {
  const existing = rows.find((r) => r.setting_key === key);
  if (existing) {
    await client.entities.site_settings.update({
      id: String(existing.id),
      data: { setting_value: value },
    });
  } else {
    await client.entities.site_settings.create({
      data: {
        setting_key: key,
        setting_value: value,
        group_name: groupName || 'general',
        label: label || key,
      },
    });
  }
  memoryCache = { ...(memoryCache ?? DEFAULT_SETTINGS), [key]: value };
  writeCache(memoryCache);
}

export function clearSettingsCache() {
  memoryCache = null;
  try {
    window.localStorage.removeItem(CACHE_KEY);
  } catch {
    /* yoksay */
  }
}

/**
 * Bileşenlerde site ayarlarını okumak için hook.
 * `settings` aktif dile göre çözülmüş değerleri içerir; `rawSettings` ham haritadır.
 */
export function useSiteSettings() {
  const { i18n } = useTranslation();
  const lang = LANGUAGE_CODES.includes(i18n.language) ? i18n.language : 'tr';
  const [rawSettings, setRawSettings] = useState<SettingsMap>(
    () => readCache() ?? { ...DEFAULT_SETTINGS }
  );
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    const map = await fetchSiteSettings(force);
    setRawSettings(map);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const settings = useMemo(() => localizeSettings(rawSettings, lang), [rawSettings, lang]);

  return { settings, rawSettings, lang, loading, reload: () => load(true) };
}

/** Kullanıcının yönetici olup olmadığını ayarlara göre belirler. */
export function isAdminUser(
  user: { email?: string; role?: string } | null | undefined,
  settings: SettingsMap
): boolean {
  if (!user) return false;
  if (typeof user.role === 'string' && user.role.toLowerCase() === 'admin') {
    return true;
  }
  const email = (user.email || '').trim().toLowerCase();
  if (!email) return false;
  const allowed = (settings.admin_emails || '')
    .split(',')
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  if (allowed.includes(email)) return true;
  return email.includes('admin');
}