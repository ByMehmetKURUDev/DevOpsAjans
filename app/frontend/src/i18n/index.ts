import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import tr from './tr.json';

/** Desteklenen dillerin tek kaynağı. */
export interface LanguageMeta {
  code: string;
  label: string;
  full: string;
  flag: string;
  dir: 'ltr' | 'rtl';
  htmlLang: string;
}

export const SUPPORTED_LANGUAGES: LanguageMeta[] = [
  { code: 'tr', label: 'TR', full: 'Türkçe', flag: '🇹🇷', dir: 'ltr', htmlLang: 'tr' },
  { code: 'en', label: 'EN', full: 'English', flag: '🇬🇧', dir: 'ltr', htmlLang: 'en' },
  { code: 'de', label: 'DE', full: 'Deutsch', flag: '🇩🇪', dir: 'ltr', htmlLang: 'de' },
  { code: 'ar', label: 'AR', full: 'العربية', flag: '🇸🇦', dir: 'rtl', htmlLang: 'ar' },
  { code: 'ru', label: 'RU', full: 'Русский', flag: '🇷🇺', dir: 'ltr', htmlLang: 'ru' },
  { code: 'zh', label: 'ZH', full: '中文', flag: '🇨🇳', dir: 'ltr', htmlLang: 'zh' },
  { code: 'hi', label: 'HI', full: 'हिन्दी', flag: '🇮🇳', dir: 'ltr', htmlLang: 'hi' },
];

export const LANGUAGE_CODES = SUPPORTED_LANGUAGES.map((l) => l.code);

export function getLanguageMeta(code: string): LanguageMeta {
  return SUPPORTED_LANGUAGES.find((l) => l.code === code) ?? SUPPORTED_LANGUAGES[0];
}

export function isRtlLanguage(code: string): boolean {
  return getLanguageMeta(code).dir === 'rtl';
}

/**
 * Çeviri paketleri talep üzerine yüklenir — ilk yüklemede yalnızca Türkçe
 * bundle'a dahil olur, diğer 6 dil ayrı chunk olarak istendiğinde iner.
 */
type Loader = () => Promise<{ default: Record<string, unknown> }>;

const LOADERS: Record<string, Loader> = {
  en: () => import('./en.json'),
  de: () => import('./de.json'),
  ar: () => import('./ar.json'),
  ru: () => import('./ru.json'),
  zh: () => import('./zh.json'),
  hi: () => import('./hi.json'),
};

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('lang') : null;
const savedLang = stored && LANGUAGE_CODES.includes(stored) ? stored : 'tr';

i18n.use(initReactI18next).init({
  resources: { tr: { translation: tr } },
  lng: 'tr',
  supportedLngs: LANGUAGE_CODES,
  fallbackLng: 'tr',
  interpolation: { escapeValue: false },
});

/**
 * Arapça ve Hintçe için gereken web fontları yalnızca o dil seçildiğinde
 * indirilir; böylece varsayılan yüklemede font yükü küçük kalır.
 */
const SCRIPT_FONTS: Record<string, string> = {
  ar: 'https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@400;500;600;700&display=swap',
  hi: 'https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap',
};

function ensureScriptFont(code: string) {
  if (typeof document === 'undefined') return;
  const href = SCRIPT_FONTS[code];
  if (!href) return;
  if (document.head.querySelector(`link[data-script-font="${code}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  link.setAttribute('data-script-font', code);
  document.head.appendChild(link);
}

/** İlgili dilin çeviri paketini (gerekiyorsa) indirir. */
export async function loadLanguage(code: string): Promise<void> {
  ensureScriptFont(code);
  if (code === 'tr' || i18n.hasResourceBundle(code, 'translation')) return;
  const loader = LOADERS[code];
  if (!loader) return;
  const mod = await loader();
  i18n.addResourceBundle(code, 'translation', mod.default, true, true);
}

/** Uygulama dilini değiştirir; paket henüz yüklenmemişse önce indirir. */
export async function changeAppLanguage(code: string): Promise<void> {
  if (!LANGUAGE_CODES.includes(code)) return;
  await loadLanguage(code);
  await i18n.changeLanguage(code);
}

/** <html lang> ve <html dir> değerlerini aktif dile göre uygular. */
export function applyDocumentDirection(code: string) {
  if (typeof document === 'undefined') return;
  const meta = getLanguageMeta(code);
  document.documentElement.lang = meta.htmlLang;
  document.documentElement.dir = meta.dir;
  document.documentElement.setAttribute('data-lang', meta.code);
}

applyDocumentDirection(savedLang);

i18n.on('languageChanged', (lng) => {
  try {
    localStorage.setItem('lang', lng);
  } catch {
    /* storage kullanılamıyorsa yoksay */
  }
  applyDocumentDirection(lng);
});

// Kayıtlı dil Türkçe değilse paketi arka planda indirip geç.
if (savedLang !== 'tr') {
  void changeAppLanguage(savedLang);
}

export default i18n;