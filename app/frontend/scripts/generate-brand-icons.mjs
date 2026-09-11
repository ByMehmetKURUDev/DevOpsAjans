/**
 * Marka ikonlarını üretir.
 *
 * `simple-icons` paketinin tamamı 3000'den fazla ikon içeriyor; hepsini
 * bundle'a koymak anlamsız. Bu betik yalnızca sitede kullanılan markaların
 * SVG yollarını çekip `src/lib/brandIcons.ts` dosyasına yazıyor.
 *
 * İkonlar markaların kendi yayımladığı işaretler; yeniden çizim yok.
 * Tanımlama amaçlı kullanılıyorlar (hangi araçlarla çalışıldığı, hangi
 * sosyal ağda hesap olduğu).
 *
 * Yeni bir marka eklemek için aşağıdaki listeye slug'ını yazıp çalıştırın:
 *   node scripts/generate-brand-icons.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as si from 'simple-icons';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Kullanılan Araçlar bölümü. Sıra ekranda göründüğü sıradır. */
const TOOLS = [
  'react', 'typescript', 'nextdotjs', 'nodedotjs', 'tailwindcss', 'vite',
  'python', 'fastapi', 'postgresql', 'redis', 'docker', 'nginx',
  'githubactions', 'git', 'github', 'figma',
  'vercel', 'cloudflare', 'supabase', 'stripe',
  'shopify', 'wordpress', 'googleanalytics', 'sentry',
];

/*
 * Not: Adobe, Amazon (AWS) ve LinkedIn simple-icons'ta YOK — bu markalar
 * kendi talepleriyle kaldırıldı. Onların işaretlerini başka bir kaynaktan
 * alıp koymuyoruz; sosyal listede LinkedIn, projede zaten bulunan çizgi
 * ikonla gösteriliyor.
 */

/** Footer ve iletişim bölümündeki sosyal ağlar. */
const SOCIALS = ['facebook', 'instagram', 'x', 'youtube', 'github', 'envato'];

function collect(slugs, label) {
  const out = {};
  const missing = [];
  for (const slug of slugs) {
    const key = 'si' + slug.charAt(0).toUpperCase() + slug.slice(1);
    const icon = si[key];
    if (!icon) { missing.push(slug); continue; }
    out[slug] = { title: icon.title, hex: icon.hex, path: icon.path };
  }
  if (missing.length > 0) console.warn(`${label}: bulunamayan slug → ${missing.join(', ')}`);
  return out;
}

const tools = collect(TOOLS, 'Araçlar');
const socials = collect(SOCIALS, 'Sosyal');

const body = `/**
 * OTOMATİK ÜRETİLDİ — elle düzenlemeyin.
 * Kaynak: scripts/generate-brand-icons.mjs  (npm run icons)
 *
 * Markaların kendi yayımladığı SVG işaretleri. 24x24 viewBox, tek yol.
 */

export interface BrandIcon {
  /** Markanın kendi yazdığı adı; erişilebilirlik etiketi olarak kullanılır. */
  title: string;
  /** Markanın resmî rengi (# olmadan). Tek renkli gösterimde kullanılmıyor. */
  hex: string;
  /** 24x24 viewBox içindeki tek SVG yolu. */
  path: string;
}

/** Kullanılan Araçlar bölümündeki markalar. */
export const TOOL_ICONS: Record<string, BrandIcon> = ${JSON.stringify(tools, null, 2)};

/** Sosyal ağ markaları. */
export const SOCIAL_ICONS: Record<string, BrandIcon> = ${JSON.stringify(socials, null, 2)};

/** Araçların varsayılan gösterim sırası. */
export const DEFAULT_TOOL_ORDER: string[] = ${JSON.stringify(Object.keys(tools), null, 2)};
`;

const target = path.join(root, 'src/lib/brandIcons.ts');
fs.writeFileSync(target, body);
console.log(`Yazıldı: src/lib/brandIcons.ts — ${Object.keys(tools).length} araç, ${Object.keys(socials).length} sosyal ikon`);
