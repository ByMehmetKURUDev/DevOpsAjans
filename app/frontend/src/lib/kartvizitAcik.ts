import type { CSSProperties } from 'react';

import { getAPIBaseURL } from '@/lib/config';
import { KOSE_DEGERLERI, ZEMIN_RENKLERI, markaDegiskenleri, markaTemasi, markaYaziTipi, type AcikMarka } from '@/lib/marka';

/**
 * Faz 4K — herkese açık kartvizit / yorum sayfasının hafif yardımcıları.
 *
 * `/kart/<slug>` ve `/yorum/<slug>` sayfaları (ve paneldeki canlı telefon
 * önizlemesi) bunu kullanıyor. Oturum yok, SDK yok: düz `fetch`. Metinler
 * kartın KENDİ dilinde (`src/i18n/kartSayfasi/<dil>.json`, i18next'e girmeden) —
 * ziyaretçinin site dili ne olursa olsun Arapça kart Arapça, sağdan sola.
 */

export interface AcikGorsel {
  id: number;
  url: string;
  genislik: number;
  yukseklik: number;
}

export interface AcikTema {
  sablon: string;
  renk: string;
  yazi_tipi: string;
  kose: string;
}

export interface AcikKart {
  durum: 'aktif';
  slug: string;
  kod: string;
  duzen: 'kartvizit' | 'bio_link';
  dil: string;
  tema: AcikTema;
  ad_soyad: string;
  unvan: string;
  sirket: string;
  tanitim: string;
  adres: string;
  harita_url: string;
  telefonlar: { etiket: string; numara: string; tip: string; tel: string }[];
  eposta: string;
  webler: { etiket: string; url: string }[];
  whatsapp_url: string;
  sosyal: { platform: string; url: string }[];
  baglantilar: { id?: string; baslik: string; url: string; simge: string }[];
  hizmetler: { baslik: string; aciklama: string }[];
  calisma_saatleri: { goster: boolean; gunler: { gun: string; acik: boolean; acilis: string; kapanis: string }[]; not: string } | null;
  foto: AcikGorsel | null;
  logo: AcikGorsel | null;
  kapak: AcikGorsel | null;
  galeri: AcikGorsel[];
  form: { acik: boolean; jeton: string | null; aydinlatma_adresi: string };
  kart_adresi: string;
  index: boolean;
  vcard_adresi: string;
  qr_adresi: string;
  /** Faz 4L: hesabın marka teması (kartın kendi teması özelse `sayfa_ozel`). */
  marka?: AcikMarka;
}

export type KartYaniti =
  | AcikKart
  | { durum: 'kilitli'; slug: string; dil: string; tema: AcikTema; index: false; marka?: AcikMarka }
  | { durum: 'yonlendir'; yonlendir: string };

export interface AcikYorum {
  durum: 'aktif';
  slug: string;
  kod: string;
  dil: string;
  isletme_adi: string;
  tesekkur: string;
  renk: string;
  logo: AcikGorsel | null;
  google_adresi: string;
  geri_bildirim: { acik: boolean; jeton: string | null; aydinlatma_adresi: string };
  marka?: AcikMarka;
}

export class AcikHata extends Error {
  constructor(public durum: number, public kod: string) {
    super(kod);
  }
}

async function acikIstek<T>(url: string, init?: RequestInit): Promise<T> {
  let y: Response;
  try {
    y = await fetch(`${getAPIBaseURL()}${url}`, { ...init, credentials: 'omit' });
  } catch {
    throw new AcikHata(0, 'ag');
  }
  if (!y.ok) {
    const g = (await y.json().catch(() => null)) as { detail?: { kod?: string } } | null;
    throw new AcikHata(y.status, g?.detail?.kod || (y.status === 404 ? 'bulunamadi' : 'genel'));
  }
  return (await y.json()) as T;
}

/** JSON gövde `text/plain` ile: ön kontrol (CORS preflight) yok, sendBeacon ile aynı biçim. */
function govde(veri: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(veri), headers: { 'Content-Type': 'text/plain;charset=UTF-8' } };
}

export const kartGetir = (adres: string, jeton?: string | null) =>
  acikIstek<KartYaniti>(`/api/v1/kart/${encodeURIComponent(adres)}${jeton ? `?j=${encodeURIComponent(jeton)}` : ''}`);
export const kartParola = (adres: string, parola: string) =>
  acikIstek<{ jeton: string | null; kart: AcikKart }>(`/api/v1/kart/${encodeURIComponent(adres)}/parola`, govde({ parola }));
export const kartMesaj = (adres: string, veri: Record<string, unknown>) =>
  acikIstek<{ ok: boolean }>(`/api/v1/kart/${encodeURIComponent(adres)}/mesaj`, govde(veri));
export const yorumGetir = (adres: string) => acikIstek<AcikYorum | { durum: 'yonlendir'; yonlendir: string }>(
  `/api/v1/yorum/${encodeURIComponent(adres)}`
);
export const yorumGeriBildirim = (adres: string, veri: Record<string, unknown>) =>
  acikIstek<{ ok: boolean }>(`/api/v1/yorum/${encodeURIComponent(adres)}/geri-bildirim`, govde(veri));

/** Analitik olayı: sayfa kapanırken de gitsin (sendBeacon; yoksa keepalive fetch). Hata yutulur. */
export function isaretGonder(yol: string, veri: Record<string, unknown>): void {
  const adres = `${getAPIBaseURL()}${yol}`;
  const metin = JSON.stringify(veri);
  try {
    if (navigator.sendBeacon && navigator.sendBeacon(adres, new Blob([metin], { type: 'text/plain;charset=UTF-8' }))) return;
  } catch {
    /* fetch'e düş */
  }
  void fetch(adres, { method: 'POST', body: metin, keepalive: true, headers: { 'Content-Type': 'text/plain;charset=UTF-8' } }).catch(
    () => undefined
  );
}

export const apiAdresi = (yol: string) => `${getAPIBaseURL()}${yol}`;

// ---------------------------------------------------------------------------
// Tema
// ---------------------------------------------------------------------------
interface Sablon {
  zemin: string;
  yuzey: string;
  cerceve: string;
  metin: string;
  soluk: string;
  koyu: boolean;
}

/** Beş hazır görünüm. Yüzeyler her zaman okunur kontrastta; vurgu rengi kullanıcıdan. */
export const SABLONLAR: Record<string, Sablon> = {
  gece: {
    zemin: 'radial-gradient(ellipse at top, #2a1450 0%, #0b0714 62%)',
    yuzey: 'rgba(255,255,255,0.06)',
    cerceve: 'rgba(255,255,255,0.12)',
    metin: '#f4f0fb',
    soluk: '#bdb6cc',
    koyu: true,
  },
  beyaz: { zemin: '#f5f6fa', yuzey: '#ffffff', cerceve: '#e5e7eb', metin: '#0f172a', soluk: '#475569', koyu: false },
  kurumsal: {
    zemin: 'linear-gradient(180deg, var(--kv-vurgu) 0, var(--kv-vurgu) 150px, #eef2f7 150px)',
    yuzey: '#ffffff',
    cerceve: '#dbe2ea',
    metin: '#0f172a',
    soluk: '#475569',
    koyu: false,
  },
  canli: {
    zemin: 'linear-gradient(160deg, var(--kv-vurgu) 0%, #f97316 100%)',
    yuzey: 'rgba(255,255,255,0.94)',
    cerceve: 'rgba(255,255,255,0.7)',
    metin: '#111827',
    soluk: '#4b5563',
    koyu: false,
  },
  doga: { zemin: '#f3f1ea', yuzey: '#fffdf7', cerceve: '#e4dfd0', metin: '#1c2a1f', soluk: '#4b5b4e', koyu: false },
};

const YAZI_TIPLERI: Record<string, string> = {
  jakarta: "'Plus Jakarta Sans', 'Inter', ui-sans-serif, system-ui, sans-serif",
  mono: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
  sistem: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', sans-serif",
};
const KOSE: Record<string, [string, string]> = {
  keskin: ['6px', '6px'],
  yumusak: ['18px', '12px'],
  yuvarlak: ['28px', '9999px'],
};

function parlaklik(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return 0;
  const kanal = (i: number) => {
    const s = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * kanal(0) + 0.7152 * kanal(2) + 0.0722 * kanal(4);
}

/** Vurgunun üstündeki yazı: beyaz mı siyah mı (WCAG kontrastı yüksek olan). */
export function vurguMetni(renk: string): string {
  const l = parlaklik(renk);
  return (1.05) / (l + 0.05) >= (l + 0.05) / 0.05 ? '#ffffff' : '#111111';
}

/** Kart kabının stili: CSS değişkenleri (`--kv-*`), yazı tipi, zemin. */
export function temaStili(tema: AcikTema, dil: string): CSSProperties {
  const s = SABLONLAR[tema.sablon] || SABLONLAR.gece;
  const [yaricap, dugme] = KOSE[tema.kose] || KOSE.yumusak;
  const renk = /^#[0-9a-f]{6}$/i.test(tema.renk) ? tema.renk : '#a855f7';
  let yazi = YAZI_TIPLERI[tema.yazi_tipi] || YAZI_TIPLERI.jakarta;
  if (dil === 'ar') yazi = `'Noto Naskh Arabic', ${yazi}`;
  if (dil === 'hi') yazi = `'Noto Sans Devanagari', ${yazi}`;
  return {
    ['--kv-vurgu' as string]: renk,
    ['--kv-vurgu-metin' as string]: vurguMetni(renk),
    ['--kv-yuzey' as string]: s.yuzey,
    ['--kv-cerceve' as string]: s.cerceve,
    ['--kv-metin' as string]: s.metin,
    ['--kv-soluk' as string]: s.soluk,
    ['--kv-yaricap' as string]: yaricap,
    ['--kv-dugme' as string]: dugme,
    background: s.zemin,
    color: s.metin,
    fontFamily: yazi,
    colorScheme: s.koyu ? 'dark' : 'light',
  } as CSSProperties;
}

/**
 * Faz 4L — marka teması kartın varsayılanı: kartın kendi teması özel değilse (`sayfa_ozel` yok)
 * marka (zemin, ana renk, köşe, yazı tipi) kart temasına çevriliyor. Döner: çizilecek tema +
 * kart kabına eklenecek stil (marka zemini, yazı tipi, `--marka-*`); marka yoksa `ek` boş.
 */
export function markaliTema(tema: AcikTema, marka: AcikMarka | null | undefined, dil: string): { tema: AcikTema; ek: CSSProperties | undefined } {
  const t = markaTemasi(marka);
  if (!t || marka?.sayfa_ozel) return { tema, ek: undefined };
  const kose = KOSE_DEGERLERI[t.kose] ? t.kose : 'yumusak';
  return {
    tema: { sablon: t.zemin === 'koyu' ? 'gece' : 'beyaz', renk: t.ana, yazi_tipi: 'jakarta', kose },
    ek: {
      ...markaDegiskenleri(t, dil),
      background: ZEMIN_RENKLERI[t.zemin].zemin,
      fontFamily: markaYaziTipi(t, dil),
    } as CSSProperties,
  };
}

/** Arapça / Hintçe kart için yazı tipi (site yalnız o dil seçilince indiriyor). */
export function yaziTipiYukle(dil: string): void {
  const adres: Record<string, string> = {
    ar: 'https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@400;500;600;700&display=swap',
    hi: 'https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700&display=swap',
  };
  const href = adres[dil];
  if (!href || typeof document === 'undefined') return;
  if (document.head.querySelector(`link[data-script-font="${dil}"]`)) return;
  const l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = href;
  l.setAttribute('data-script-font', dil);
  document.head.appendChild(l);
}

// ---------------------------------------------------------------------------
// Kartın kendi dilindeki metinler
// ---------------------------------------------------------------------------
type Sozluk = Record<string, unknown>;
const PAKETLER = import.meta.glob<{ default: { kartSayfasi: Sozluk } }>('../i18n/kartSayfasi/*.json');
const onbellek = new Map<string, Sozluk>();
export const KART_DILLERI = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];

export async function metinleriYukle(dil: string): Promise<Sozluk> {
  const d = KART_DILLERI.includes(dil) ? dil : 'tr';
  const hazir = onbellek.get(d);
  if (hazir) return hazir;
  const yukleyici = PAKETLER[`../i18n/kartSayfasi/${d}.json`];
  const s = yukleyici ? (await yukleyici()).default.kartSayfasi : {};
  onbellek.set(d, s);
  return s;
}

export type Cevirmen = (anahtar: string, degerler?: Record<string, string | number>) => string;

export function cevirmen(sozluk: Sozluk | null): Cevirmen {
  return (anahtar, degerler) => {
    let deger: unknown = sozluk;
    for (const p of anahtar.split('.')) deger = deger && typeof deger === 'object' ? (deger as Sozluk)[p] : undefined;
    let metin = typeof deger === 'string' ? deger : '';
    if (degerler) for (const [k, v] of Object.entries(degerler)) metin = metin.split(`{{${k}}}`).join(String(v));
    return metin;
  };
}
