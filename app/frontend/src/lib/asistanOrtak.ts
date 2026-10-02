import i18n from 'i18next';

import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 5A — AI asistan sohbet penceresinin ortak parçaları (herkese açık sayfa
 * `/asistan/<anahtar>` ve panel önizlemesi). Küçük tutuluyor: herkese açık
 * sayfanın paketine giriyor.
 */

export const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
export type AsistanDili = (typeof DILLER)[number];

export interface AcikYapilandirma {
  anahtar: string;
  ad: string;
  karsilama: string | null;
  varsayilan_karsilama: string;
  renk: string;
  avatar: string | null;
  onerilen_sorular: string[];
  dil: 'otomatik' | AsistanDili;
  ui_dil: AsistanDili | null;
  aydinlatma: { metin: string | null; baglanti: string; ozel: boolean };
  mesai: { aktif: boolean; ici: boolean | null };
  mesaj_siniri: number;
  oturum: string;
  ajans: boolean;
  onizleme: boolean;
  aktif: boolean;
}

export interface KaynakAtfi {
  no: number;
  kaynak_id: number;
  baslik: string | null;
  adres: string | null;
}

export interface MesajYaniti {
  mod: 'normal' | 'butce';
  yanit: string;
  kaynaklar: KaynakAtfi[];
  bilinmiyor: boolean;
  devir_onerisi: boolean;
  mesaj_id: number | null;
  mesai?: boolean | null;
}

export interface EkranMesaji {
  rol: 'kullanici' | 'asistan';
  metin: string;
  kaynaklar?: KaynakAtfi[];
  devir?: boolean;
  hata?: boolean;
}

export function dilSec(...adaylar: (string | null | undefined)[]): AsistanDili {
  for (const a of adaylar) {
    const d = String(a || '').toLowerCase().slice(0, 2);
    if ((DILLER as readonly string[]).includes(d)) return d as AsistanDili;
  }
  return 'tr';
}

const PAKETLER = import.meta.glob<{ default: Record<string, unknown> }>('../i18n/ek/asistanSayfa/*.json');
const yuklenen = new Set<string>();

/** Herkese açık pencerenin metin paketi (Türkçe yedekle birlikte). */
export async function asistanPaketiYukle(dil: string): Promise<void> {
  for (const d of new Set(['tr', dil])) {
    if (yuklenen.has(d)) continue;
    const y = PAKETLER[`../i18n/ek/asistanSayfa/${d}.json`];
    if (!y) continue;
    const mod = await y();
    i18n.addResourceBundle(d, 'translation', mod.default, true, false);
    yuklenen.add(d);
  }
}

/** Marka renginin üstünde okunur yazı rengi (WCAG göreli parlaklık). */
export function ustYaziRengi(renk: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(renk || '');
  if (!m) return '#ffffff';
  const n = parseInt(m[1], 16);
  const kanal = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const l = 0.2126 * kanal((n >> 16) & 255) + 0.7152 * kanal((n >> 8) & 255) + 0.0722 * kanal(n & 255);
  return l > 0.45 ? '#111827' : '#ffffff';
}

export function depoOku<T>(anahtar: string): T | null {
  try {
    const ham = sessionStorage.getItem(anahtar);
    return ham ? (JSON.parse(ham) as T) : null;
  } catch {
    return null;
  }
}

export function depoYaz(anahtar: string, deger: unknown): void {
  try {
    sessionStorage.setItem(anahtar, JSON.stringify(deger));
  } catch {
    /* gizli sekme / kota: yalnız bellekte */
  }
}

export class AcikHata extends Error {
  constructor(
    public durum: number,
    public kod: string
  ) {
    super(kod);
  }
}

export async function acikIstek<T>(yol: string, init: RequestInit = {}, ekBasliklar: Record<string, string> = {}): Promise<T> {
  let y: Response;
  try {
    y = await fetch(`${getAPIBaseURL()}${yol}`, {
      ...init,
      headers: { accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...ekBasliklar },
    });
  } catch {
    throw new AcikHata(0, 'ag');
  }
  const g = (await y.json().catch(() => null)) as { detail?: { kod?: string } } | null;
  if (!y.ok) {
    const kod = g && typeof g.detail === 'object' && g.detail && typeof g.detail.kod === 'string' ? g.detail.kod : y.status === 429 ? 'cok_hizli' : 'genel';
    throw new AcikHata(y.status, kod);
  }
  return g as unknown as T;
}

/** Oturum jetonunun ömrü (sunucuda 12 saat); daha eskiyse yenisi kullanılır. */
export function oturumTaze(oturum: string | null | undefined): boolean {
  const zaman = Number(String(oturum || '').split('.')[0]);
  return Number.isFinite(zaman) && Date.now() - zaman < 11 * 3600 * 1000;
}
