/**
 * Faz 6E — etkinlik ve bilet: herkese açık sayfalar (etkinlik, bilet, kapı okutma) ile panelin
 * ortak türleri ve yardımcıları. Ana pakete girmez — yalnız etkinlik sayfası / sekmesi açılınca iner.
 *
 * Zaman kuralı: sunucu UTC saklar; gösterim etkinliğin saat diliminde (`Intl`).
 * Para: kuruş tamsayı (`fiyat`, `toplam`); yazarken 100'e bölünür.
 */

import { getAPIBaseURL } from '@/lib/config';
import { seciliHesap } from '@/lib/hesapSecimi';

export const ETKINLIK_DILLERI = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
export type EtkinlikDili = (typeof ETKINLIK_DILLERI)[number];
export const DIL_ADLARI: Record<EtkinlikDili, string> = {
  tr: 'Türkçe',
  en: 'English',
  de: 'Deutsch',
  ru: 'Русский',
  zh: '中文',
  hi: 'हिन्दी',
  ar: 'العربية',
};

export type Bicim = 'yuz_yuze' | 'online' | 'karma';
export type EtkinlikDurumu = 'taslak' | 'yayinda' | 'iptal' | 'tamamlandi';
export type TelefonKurali = 'gizli' | 'istege_bagli' | 'zorunlu';
export type BiletDurumu = 'gecerli' | 'odeme_bekliyor' | 'iptal';
export type OkutmaSonucu =
  | 'gecerli'
  | 'zaten_girdi'
  | 'gecersiz'
  | 'iptal'
  | 'farkli_etkinlik'
  | 'odeme_bekliyor'
  | 'etkinlik_iptal';

export interface Soru {
  id: string;
  etiket: string;
  tur: 'metin' | 'uzun' | 'secim' | 'onay';
  zorunlu: boolean;
  secenekler: string[];
}

export interface Oturum {
  ad: string;
  baslangic: string;
  bitis: string;
}

export interface Sayac {
  toplam: number;
  giren: number;
  kalan: number;
  kapasite: number | null;
  turler: { id: number; ad: string; toplam: number; giren: number }[];
}

export interface OkutmaYaniti {
  sonuc: OkutmaSonucu;
  bilet: { kod: string; tur: string; ad: string | null; giris_at: string | null } | null;
  sayac: Sayac;
  zaman: string;
}

export function api(): string {
  return getAPIBaseURL();
}

export function hataKodu(govde: unknown): string {
  const d = (govde as { detail?: { kod?: string } } | null)?.detail;
  return d && typeof d === 'object' && typeof d.kod === 'string' ? d.kod : 'genel';
}

/** Ziyaretçinin dili: ?dil= → kayıtlı → tarayıcı → yedek. */
export function dilSec(istenen: string | null, kayitli: string | null, yedek: string): EtkinlikDili {
  const tarayici = typeof navigator !== 'undefined' ? (navigator.languages || [navigator.language]).map((x) => (x || '').slice(0, 2)) : [];
  const aday = [istenen, kayitli, ...tarayici, yedek].find((d) => d && (ETKINLIK_DILLERI as readonly string[]).includes(d));
  return (aday as EtkinlikDili) || 'tr';
}

export function paraYaz(kurus: number, para: string, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: para || 'TRY' }).format((kurus || 0) / 100);
  } catch {
    return `${((kurus || 0) / 100).toFixed(2)} ${para}`;
  }
}

export function tarihYaz(iso: string | null | undefined, tz: string, dil: string, secenek: Intl.DateTimeFormatOptions = { dateStyle: 'full' }): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(dil, { ...secenek, timeZone: tz }).format(new Date(iso));
  } catch {
    return iso.slice(0, 10);
  }
}

export function saatYaz(iso: string | null | undefined, tz: string, dil: string): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(dil, { hour: '2-digit', minute: '2-digit', timeZone: tz }).format(new Date(iso));
  } catch {
    return iso.slice(11, 16);
  }
}

/** "5 Kasım 2026 Perşembe · 10:00 – 17:00" (aynı gün) ya da iki tarih. */
export function aralikYaz(bas: string, bit: string, tz: string, dil: string): string {
  const g1 = tarihYaz(bas, tz, dil);
  const g2 = tarihYaz(bit, tz, dil);
  return g1 === g2 ? `${g1} · ${saatYaz(bas, tz, dil)} – ${saatYaz(bit, tz, dil)}` : `${g1} ${saatYaz(bas, tz, dil)} – ${g2} ${saatYaz(bit, tz, dil)}`;
}

export function depoOku(anahtar: string): string | null {
  try {
    return localStorage.getItem(anahtar);
  } catch {
    return null;
  }
}

export function depoYaz(anahtar: string, deger: string): void {
  try {
    localStorage.setItem(anahtar, deger);
  } catch {
    /* gizli sekme: yalnız bellekte */
  }
}

export function sorgu(ad: string): string | null {
  try {
    return new URLSearchParams(window.location.search).get(ad);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Kapı okutma istemcisi: görevli jetonu (girişsiz) ya da panel oturumu (ekip izni)
// ---------------------------------------------------------------------------
export interface OkutmaIstemcisi {
  /** Yerel kuyruk anahtarı (çevrimdışı okutmalar). */
  anahtar: string;
  ozet(): Promise<{ baslik: string; baslangic: string; bitis: string; saat_dilimi: string; dil: string; renk?: string; durum: string; sayac: Sayac }>;
  okut(kod: string, cevrimdisi?: boolean, zaman?: string): Promise<OkutmaYaniti>;
  sayac(): Promise<Sayac>;
}

export class OkutmaHatasi extends Error {
  constructor(public durum: number, public kod: string) {
    super(kod);
  }
}

async function jsonIstek<T>(yol: string, init: RequestInit = {}): Promise<T> {
  let y: Response;
  try {
    y = await fetch(`${api()}${yol}`, { ...init, headers: { accept: 'application/json', ...(init.headers as Record<string, string> | undefined) } });
  } catch {
    throw new OkutmaHatasi(0, 'ag');
  }
  const g = await y.json().catch(() => null);
  if (!y.ok) throw new OkutmaHatasi(y.status, hataKodu(g));
  return g as T;
}

export function gorevliIstemcisi(jeton: string): OkutmaIstemcisi {
  const t = `/api/v1/etkinlik/giris/${encodeURIComponent(jeton)}`;
  return {
    anahtar: `mk-etkinlik-kuyruk-g-${jeton.split('-')[0]}`,
    async ozet() {
      const g = await jsonIstek<{ etkinlik: { baslik: string; baslangic: string; bitis: string; saat_dilimi: string; dil: string; renk: string; durum: string }; sayac: Sayac }>(t);
      return { ...g.etkinlik, sayac: g.sayac };
    },
    okut: (kod, cevrimdisi = false, zaman) =>
      jsonIstek<OkutmaYaniti>(`${t}/okut`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kod, cevrimdisi, zaman }) }),
    sayac: () => jsonIstek<Sayac>(`${t}/sayac`),
  };
}

function oturumBasliklari(): Record<string, string> {
  const b: Record<string, string> = {};
  try {
    const j = localStorage.getItem('token');
    if (j) b.Authorization = `Bearer ${j}`;
  } catch {
    /* depolama yok */
  }
  const h = seciliHesap();
  if (h) b['X-MK-Hesap'] = h;
  return b;
}

export function panelIstemcisi(eid: number, yonetici: boolean): OkutmaIstemcisi {
  const t = `${yonetici ? '/api/v1/etkinlik/yonetim' : '/api/v1/etkinliklerim'}/${eid}`;
  return {
    anahtar: `mk-etkinlik-kuyruk-p-${eid}`,
    async ozet() {
      const g = await jsonIstek<Sayac & { baslik: string; baslangic: string; bitis: string; saat_dilimi: string; durum: string }>(`${t}/sayac`, { headers: oturumBasliklari() });
      return { baslik: g.baslik, baslangic: g.baslangic, bitis: g.bitis, saat_dilimi: g.saat_dilimi, dil: '', durum: g.durum, sayac: g };
    },
    okut: (kod, cevrimdisi = false, zaman) =>
      jsonIstek<OkutmaYaniti>(`${t}/okut`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...oturumBasliklari() },
        body: JSON.stringify({ kod, cevrimdisi, zaman }),
      }),
    sayac: () => jsonIstek<Sayac>(`${t}/sayac`, { headers: oturumBasliklari() }),
  };
}

/** Çevrimdışı kuyruk: en çok 50 okutma; bağlantı gelince sırayla gönderilir (sunucu çift girişi engeller). */
export const KUYRUK_EN_COK = 50;

export interface KuyrukOgesi {
  kod: string;
  zaman: string;
}

export function kuyrukOku(anahtar: string): KuyrukOgesi[] {
  try {
    const d = JSON.parse(depoOku(anahtar) || '[]');
    return Array.isArray(d) ? d.filter((x) => x && typeof x.kod === 'string' && typeof x.zaman === 'string').slice(-KUYRUK_EN_COK) : [];
  } catch {
    return [];
  }
}

export function kuyrukYaz(anahtar: string, liste: KuyrukOgesi[]): void {
  depoYaz(anahtar, JSON.stringify(liste.slice(-KUYRUK_EN_COK)));
}
