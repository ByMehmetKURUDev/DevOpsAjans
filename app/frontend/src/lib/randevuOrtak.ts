/**
 * Faz 5R — randevu: herkese açık sayfa ve panelin ortak türleri ve yardımcıları.
 *
 * Saat dilimi kuralı: sunucu UTC saklıyor ve müsait saatleri ziyaretçinin seçtiği
 * saat diliminde günlere bölüyor; tarayıcı yalnız gösteriyor (`Intl`). Bu dosya
 * ana pakete girmez — yalnız randevu sayfası / sekmesi açılınca iner.
 */

export const RANDEVU_DILLERI = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
export type RandevuDili = (typeof RANDEVU_DILLERI)[number];
export const DIL_ADLARI: Record<RandevuDili, string> = {
  tr: 'Türkçe',
  en: 'English',
  de: 'Deutsch',
  ru: 'Русский',
  zh: '中文',
  hi: 'हिन्दी',
  ar: 'العربية',
};

export type KonumTuru = 'jitsi' | 'baglanti' | 'telefon' | 'yuz_yuze';
export type AtamaTuru = 'kisi' | 'sirali' | 'ilk_musait';
export type TelefonSecenegi = 'gizli' | 'istege_bagli' | 'zorunlu';
export type SoruTuru = 'metin' | 'uzun' | 'secim' | 'onay';
export type Aralik = [string, string];
export type Haftalik = Record<string, Aralik[]>;

export interface Soru {
  id: string;
  etiket: string;
  tur: SoruTuru;
  zorunlu: boolean;
  secenekler: string[];
}

export interface Slot {
  bas: string;
  saat: string;
  kalan: number;
}

export interface Musaitlik {
  tz: string;
  sayfa_tz: string;
  bas: string;
  gun: number;
  gunler: Record<string, Slot[]>;
  kapasite: number;
  en_gec: string;
}

/** Tarayıcının saat dilimi (yoksa İstanbul). */
export function tarayiciSaatDilimi(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Istanbul';
  } catch {
    return 'Europe/Istanbul';
  }
}

const YEDEK_DILIMLER = [
  'Europe/Istanbul', 'Europe/London', 'Europe/Berlin', 'Europe/Paris', 'Europe/Amsterdam', 'Europe/Moscow',
  'Europe/Kyiv', 'Asia/Baku', 'Asia/Dubai', 'Asia/Riyadh', 'Asia/Tehran', 'Asia/Karachi', 'Asia/Kolkata',
  'Asia/Shanghai', 'Asia/Tokyo', 'Australia/Sydney', 'Africa/Cairo', 'America/New_York', 'America/Chicago',
  'America/Denver', 'America/Los_Angeles', 'America/Sao_Paulo', 'UTC',
];

/** Seçicide gösterilecek saat dilimleri (tarayıcı destekliyorsa hepsi). */
export function saatDilimleri(ek: string[] = []): string[] {
  let liste: string[] = [];
  try {
    const f = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf;
    if (f) liste = f('timeZone');
  } catch {
    liste = [];
  }
  if (!liste.length) liste = YEDEK_DILIMLER;
  return [...new Set([...ek.filter(Boolean), ...liste])];
}

/** "GMT+3" gibi kısa fark. */
export function tzFarki(tz: string, dil: string, an: Date = new Date()): string {
  try {
    const parca = new Intl.DateTimeFormat(dil, { timeZone: tz, timeZoneName: 'shortOffset' })
      .formatToParts(an)
      .find((p) => p.type === 'timeZoneName');
    return parca?.value || '';
  } catch {
    return '';
  }
}

export function saatYaz(iso: string, tz: string, dil: string): string {
  try {
    return new Intl.DateTimeFormat(dil, { hour: '2-digit', minute: '2-digit', timeZone: tz }).format(new Date(iso));
  } catch {
    return iso.slice(11, 16);
  }
}

export function tarihYaz(iso: string, tz: string, dil: string, secenek: Intl.DateTimeFormatOptions = { dateStyle: 'full' }): string {
  try {
    return new Intl.DateTimeFormat(dil, { ...secenek, timeZone: tz }).format(new Date(iso));
  } catch {
    return iso.slice(0, 10);
  }
}

/** "YYYY-AA-GG" → o günün (UTC öğlen) Date'i: yalnız gün/ay adı yazmak için. */
export function gunTarihi(gun: string): Date {
  const [y, a, g] = gun.split('-').map(Number);
  return new Date(Date.UTC(y, a - 1, g, 12));
}

export function gunAdiYaz(gun: string, dil: string, secenek: Intl.DateTimeFormatOptions = { weekday: 'long', day: 'numeric', month: 'long' }): string {
  try {
    return new Intl.DateTimeFormat(dil, { ...secenek, timeZone: 'UTC' }).format(gunTarihi(gun));
  } catch {
    return gun;
  }
}

export function ayAdiYaz(yil: number, ay: number, dil: string): string {
  try {
    return new Intl.DateTimeFormat(dil, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(yil, ay - 1, 15)));
  } catch {
    return `${yil}-${String(ay).padStart(2, '0')}`;
  }
}

/** Pazartesiden başlayan kısa gün adları. */
export function haftaGunleri(dil: string): string[] {
  const sonuc: string[] = [];
  for (let i = 0; i < 7; i++) {
    try {
      // 5 Ocak 2026 Pazartesi.
      sonuc.push(new Intl.DateTimeFormat(dil, { weekday: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(2026, 0, 5 + i, 12))));
    } catch {
      sonuc.push(String(i + 1));
    }
  }
  return sonuc;
}

export function isoGun(yil: number, ay: number, gun: number): string {
  return `${yil}-${String(ay).padStart(2, '0')}-${String(gun).padStart(2, '0')}`;
}

export function aydakiGunSayisi(yil: number, ay: number): number {
  return new Date(Date.UTC(yil, ay, 0)).getUTCDate();
}

/** Ay ızgarası: pazartesiyle başlayan haftalar; ay dışı hücre `null`. */
export function ayIzgarasi(yil: number, ay: number): (string | null)[][] {
  const ilk = new Date(Date.UTC(yil, ay - 1, 1));
  const bosluk = (ilk.getUTCDay() + 6) % 7;
  const gunler = aydakiGunSayisi(yil, ay);
  const hucreler: (string | null)[] = Array(bosluk).fill(null);
  for (let g = 1; g <= gunler; g++) hucreler.push(isoGun(yil, ay, g));
  while (hucreler.length % 7) hucreler.push(null);
  const haftalar: (string | null)[][] = [];
  for (let i = 0; i < hucreler.length; i += 7) haftalar.push(hucreler.slice(i, i + 7));
  return haftalar;
}

/** Saat dilimindeki bugün (YYYY-AA-GG). */
export function bugun(tz: string): string {
  try {
    const p = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    return p.slice(0, 10);
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

export function hataKodu(govde: unknown): string {
  const d = (govde as { detail?: { kod?: string } } | null)?.detail;
  return d && typeof d === 'object' && typeof d.kod === 'string' ? d.kod : 'genel';
}

/** Ziyaretçinin dili: ?dil= → kayıtlı → tarayıcı → yedek. */
export function dilSec(istenen: string | null, kayitli: string | null, yedek: string): RandevuDili {
  const tarayici = typeof navigator !== 'undefined' ? (navigator.languages || [navigator.language]).map((x) => (x || '').slice(0, 2)) : [];
  const aday = [istenen, kayitli, ...tarayici, yedek].find((d) => d && (RANDEVU_DILLERI as readonly string[]).includes(d));
  return (aday as RandevuDili) || 'tr';
}
