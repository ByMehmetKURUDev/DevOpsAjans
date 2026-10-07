import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import type { MarkaKose, MarkaLogo, MarkaYaziTipi, MarkaZemin } from '@/lib/marka';
import { client } from '@/lib/sdkClient';

/**
 * Faz 4L — Marka teması: panel uçları.
 *
 * Müşteri `/api/v1/markam` (etkin hesap `X-MK-Hesap`; yazma yalnız hesap sahibi / hesap
 * yöneticisi), yönetici `/api/v1/marka/yonetim/<eposta>`. Rozet (`rozet_gizle`) bu uçlardan
 * değil, yöneticinin modül ayarından (`/api/v1/moduller/musteri/<eposta>/marka_temasi`).
 */

export interface KontrastSatiri {
  oran: number;
  yeterli: boolean;
  oneri: string | null;
}

export interface PanelMarka {
  hesap_email: string;
  kayitli: boolean;
  ad: string;
  ana_renk: string;
  vurgu_rengi: string;
  zemin: MarkaZemin;
  kose: MarkaKose;
  yazi_tipi: MarkaYaziTipi;
  logo: (MarkaLogo & { boyut?: number | null }) | null;
  denetim: { esik: number; ana: KontrastSatiri & { yazi: string }; vurgu: KontrastSatiri & { zemin: string } };
  modul_acik: boolean;
  rozet_gizle: boolean;
  updated_at: string | null;
}

export type MarkaGirdisi = Partial<Pick<PanelMarka, 'ad' | 'ana_renk' | 'vurgu_rengi' | 'zemin' | 'kose' | 'yazi_tipi'>>;

export class MarkaUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): MarkaUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const d = detay as { kod: string; alan?: string };
    return new MarkaUcHatasi(durum, d.kod, d.alan ?? null);
  }
  if (durum === 429) return new MarkaUcHatasi(durum, 'cok_hizli');
  if (durum === 413) return new MarkaUcHatasi(durum, 'logo_buyuk');
  return new MarkaUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
}

function govdeyiAc<T>(yanit: unknown): T {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) return (yanit as { data: T }).data;
  return yanit as T;
}

async function istek<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    return govdeyiAc<T>(await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> | undefined }));
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    throw hataCoz(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

function oturumBasliklari(): Record<string, string> {
  const b: Record<string, string> = { ...hesapBasliklari() };
  try {
    const j = localStorage.getItem('token');
    if (j) b.Authorization = `Bearer ${j}`;
  } catch {
    /* depolama yok */
  }
  return b;
}

export function markaApi(eposta?: string) {
  const T = eposta ? `/api/v1/marka/yonetim/${encodeURIComponent(eposta)}` : '/api/v1/markam';
  return {
    getir: () => istek<PanelMarka>('GET', T),
    kaydet: (g: MarkaGirdisi) => istek<PanelMarka>('PUT', T, g),
    sifirla: () => istek<PanelMarka>('DELETE', T),
    logoKaldir: () => istek<PanelMarka>('DELETE', `${T}/logo`),
    async logoYukle(dosya: File): Promise<PanelMarka> {
      const form = new FormData();
      form.append('dosya', dosya);
      let y: Response;
      try {
        y = await fetch(`${getAPIBaseURL()}${T}/logo`, { method: 'POST', body: form, headers: oturumBasliklari() });
      } catch {
        throw new MarkaUcHatasi(0, 'ag');
      }
      const g = (await y.json().catch(() => null)) as (PanelMarka & { detail?: unknown }) | null;
      if (!y.ok) throw hataCoz(y.status, g?.detail);
      return g as PanelMarka;
    },
  };
}

// ---------------------------------------------------------------------------
// Canlı kontrast (WCAG 2.1, arka uç `services/marka.py` ile aynı formül) — kaydetmeden önce gösterim için.
// ---------------------------------------------------------------------------
const RENK = /^#[0-9a-f]{6}$/i;

function kanallar(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [number, number, number];
}

export function parlaklik(hex: string): number {
  const d = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = kanallar(hex);
  return 0.2126 * d(r) + 0.7152 * d(g) + 0.0722 * d(b);
}

export function kontrast(a: string, b: string): number {
  const la = parlaklik(a);
  const lb = parlaklik(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export const YAZI_ACIK = '#ffffff';
export const YAZI_KOYU = '#111111';
export const AA = 4.5;

export const ustYazi = (hex: string) => (kontrast(hex, YAZI_ACIK) >= kontrast(hex, YAZI_KOYU) ? YAZI_ACIK : YAZI_KOYU);

function hsl(hex: string): [number, number, number] {
  const [r, g, b] = kanallar(hex);
  const mx = Math.max(r, g, b);
  const mn = Math.min(r, g, b);
  const l = (mx + mn) / 2;
  if (mx === mn) return [0, 0, l];
  const d = mx - mn;
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  let h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h /= 6;
  return [h, s, l];
}

function hexYap(h: number, s: number, l: number): string {
  const f = (p: number, q: number, t: number) => {
    let x = t;
    if (x < 0) x += 1;
    if (x > 1) x -= 1;
    if (x < 1 / 6) return p + (q - p) * 6 * x;
    if (x < 1 / 2) return q;
    if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
    return p;
  };
  let r = l;
  let g = l;
  let b = l;
  if (s !== 0) {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = f(p, q, h + 1 / 3);
    g = f(p, q, h);
    b = f(p, q, h - 1 / 3);
  }
  return `#${[r, g, b].map((x) => Math.round(Math.max(0, Math.min(1, x)) * 255).toString(16).padStart(2, '0')).join('')}`;
}

/** Tonu koruyup açıklığı değiştirerek koşulu sağlayan en yakın renk (yoksa null). */
export function renkOnerisi(hex: string, yeterli: (c: string) => boolean): string | null {
  if (!RENK.test(hex)) return null;
  const [h, s, l0] = hsl(hex);
  let enIyi: [number, string] | null = null;
  for (const yon of [-1, 1]) {
    for (let adim = 1; adim <= 100; adim++) {
      const l = l0 + (yon * adim) / 100;
      if (l < 0 || l > 1) break;
      const aday = hexYap(h, s, l);
      if (yeterli(aday)) {
        if (!enIyi || adim < enIyi[0]) enIyi = [adim, aday];
        break;
      }
    }
  }
  return enIyi ? enIyi[1] : null;
}

export function canliDenetim(ana: string, vurgu: string, zeminRengi: string) {
  const anaGecerli = RENK.test(ana);
  const vurguGecerli = RENK.test(vurgu);
  const yazi = anaGecerli ? ustYazi(ana) : YAZI_ACIK;
  const anaOran = anaGecerli ? kontrast(ana, yazi) : 0;
  const vurguOran = vurguGecerli ? kontrast(vurgu, zeminRengi) : 0;
  return {
    ana: {
      yazi,
      oran: Math.round(anaOran * 100) / 100,
      yeterli: anaOran >= AA,
      oneri: anaGecerli && anaOran < AA ? renkOnerisi(ana, (c) => kontrast(c, ustYazi(c)) >= AA) : null,
    },
    vurgu: {
      oran: Math.round(vurguOran * 100) / 100,
      yeterli: vurguOran >= AA,
      oneri: vurguGecerli && vurguOran < AA ? renkOnerisi(vurgu, (c) => kontrast(c, zeminRengi) >= AA) : null,
    },
  };
}
