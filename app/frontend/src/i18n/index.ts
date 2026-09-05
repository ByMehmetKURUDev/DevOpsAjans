import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './en.json';
import tr from './tr.json';
import de from './de.json';
import ar from './ar.json';
import ru from './ru.json';
import zh from './zh.json';
import hi from './hi.json';

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

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('lang') : null;
const savedLang = stored && LANGUAGE_CODES.includes(stored) ? stored : 'tr';

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    tr: { translation: tr },
    de: { translation: de },
    ar: { translation: ar },
    ru: { translation: ru },
    zh: { translation: zh },
    hi: { translation: hi },
  },
  lng: savedLang,
  supportedLngs: LANGUAGE_CODES,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

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
  localStorage.setItem('lang', lng);
  applyDocumentDirection(lng);
});

export default i18n;