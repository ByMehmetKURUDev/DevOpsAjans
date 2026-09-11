import type { SettingsMap } from '@/lib/siteSettings';

/**
 * Sayfa bölümlerinin kayıt defteri.
 *
 * Her sayfa, sıralanabilir ve gizlenebilir bölümlerden oluşuyor. Sıra ve
 * görünürlük panelde `page_<sayfa>_sections` anahtarında saklanıyor:
 *
 *   "hero:1,capabilities:1,process:1,packages:0,..."
 *
 * Bu biçim bilerek düz metin: site ayarları anahtar/değer deposu, JSON
 * saklamak için ayrı bir alan gerekmiyor ve panelde okunabiliyor.
 *
 * Kodda tanımlı olmayan bir anahtar yok sayılır, ayarda geçmeyen bir bölüm
 * varsayılan sırasının sonuna eklenir — böylece yeni bir bölüm eklendiğinde
 * paneldeki eski kayıt sayfayı kırmıyor, yeni bölüm kendiliğinden görünüyor.
 */
export interface SectionDef {
  key: string;
  /** Panelde gösterilen ad (i18n anahtarı). */
  labelKey: string;
  /** Kapatılamayan bölümler: sayfa bunlarsız anlamsız kalır. */
  locked?: boolean;
}

export const PAGE_SECTIONS: Record<string, SectionDef[]> = {
  home: [
    { key: 'hero', labelKey: 'pageSections.hero', locked: true },
    { key: 'capabilities', labelKey: 'pageSections.capabilities' },
    { key: 'process', labelKey: 'pageSections.process' },
    { key: 'packages', labelKey: 'pageSections.packages' },
    { key: 'tech', labelKey: 'pageSections.tech' },
    { key: 'caseCategories', labelKey: 'pageSections.caseCategories' },
    { key: 'testimonials', labelKey: 'pageSections.testimonials' },
    { key: 'cta', labelKey: 'pageSections.cta' },
  ],
  services: [
    { key: 'about', labelKey: 'pageSections.about', locked: true },
    { key: 'values', labelKey: 'pageSections.values' },
    { key: 'services', labelKey: 'pageSections.services' },
    { key: 'timeline', labelKey: 'pageSections.timeline' },
    { key: 'packages', labelKey: 'pageSections.packages' },
    { key: 'testimonials', labelKey: 'pageSections.testimonials' },
    { key: 'tools', labelKey: 'pageSections.tools' },
  ],
  portfolio: [
    { key: 'header', labelKey: 'pageSections.header', locked: true },
    { key: 'filters', labelKey: 'pageSections.filters' },
    { key: 'grid', labelKey: 'pageSections.grid', locked: true },
    { key: 'timeline', labelKey: 'pageSections.timeline' },
    { key: 'testimonials', labelKey: 'pageSections.testimonials' },
    { key: 'tools', labelKey: 'pageSections.tools' },
  ],
  contact: [
    { key: 'intro', labelKey: 'pageSections.intro', locked: true },
    { key: 'channels', labelKey: 'pageSections.channels' },
    { key: 'social', labelKey: 'pageSections.social' },
    { key: 'form', labelKey: 'pageSections.form', locked: true },
  ],
};

export type PageKey = keyof typeof PAGE_SECTIONS;

export const PAGE_KEYS = Object.keys(PAGE_SECTIONS);

/** Bir sayfanın ayar anahtarı. */
export function sectionsSettingKey(page: string): string {
  return `page_${page}_sections`;
}

export interface ResolvedSection extends SectionDef {
  visible: boolean;
}

/**
 * Panel kaydını koddaki tanımla birleştirir.
 *
 * Kayıt bozuk ya da eksikse varsayılana düşer; hiçbir koşulda boş liste
 * dönmez — panelde yapılan bir yazım hatası sayfayı boşaltmamalı.
 */
export function resolveSections(page: string, settings: SettingsMap): ResolvedSection[] {
  const defs = PAGE_SECTIONS[page];
  if (!defs) return [];

  const raw = (settings[sectionsSettingKey(page)] || '').trim();
  if (!raw) return defs.map((def) => ({ ...def, visible: true }));

  const kayit = new Map<string, boolean>();
  raw.split(',').forEach((parca) => {
    const [key, deger] = parca.split(':').map((x) => x.trim());
    if (key) kayit.set(key, deger !== '0');
  });

  const bilinen = new Map(defs.map((def) => [def.key, def]));
  const sirali: ResolvedSection[] = [];

  // Önce paneldeki sıra.
  for (const [key, visible] of kayit) {
    const def = bilinen.get(key);
    if (!def) continue; // Kodda kalmayan eski bölüm sessizce düşer.
    sirali.push({ ...def, visible: def.locked ? true : visible });
    bilinen.delete(key);
  }

  // Panelde hiç geçmeyen yeni bölümler sona eklenir ve açık gelir.
  for (const def of defs) {
    if (bilinen.has(def.key)) sirali.push({ ...def, visible: true });
  }

  return sirali.length > 0 ? sirali : defs.map((def) => ({ ...def, visible: true }));
}

/** Panelin kaydettiği biçim. */
export function serializeSections(sections: ResolvedSection[]): string {
  return sections.map((s) => `${s.key}:${s.visible ? 1 : 0}`).join(',');
}

/** Sayfanın göstereceği bölüm anahtarları, sırasıyla. */
export function visibleSectionKeys(page: string, settings: SettingsMap): string[] {
  return resolveSections(page, settings)
    .filter((s) => s.visible)
    .map((s) => s.key);
}
