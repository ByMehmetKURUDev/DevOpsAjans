import { client } from '@/lib/sdkClient';

/**
 * Faz 2H — müşteri siteleri için teknik SEO + Core Web Vitals izleme (modül #31).
 *
 * Müşteri   GET  /api/v1/sitelerim/<id>/seo-gecmisi?gun=90
 *           POST /api/v1/sitelerim/<id>/seo-tara           (site başına 24 saatte 1)
 * Yönetici  GET  /api/v1/site-bakim/seo-ozet
 *           GET  /api/v1/site-bakim/<id>/seo-gecmisi?gun=90
 *           POST /api/v1/site-bakim/<id>/seo-tara          (sınırsız)
 *           PUT  /api/v1/site-bakim/<id>/seo-ayar          {tarama_gun: 0..90}
 *
 * Bulgu metinleri sunucudan gelmiyor: `kod` + `deger` → `siteAnalizi.bulgu.<kod>`
 * (site analizi ek paketi); bu modülün kendi metinleri `seoIzleme` ek paketinde.
 */

export type Seviye = 'hata' | 'uyari' | 'bilgi' | 'iyi';
export type CwvDurumu = 'iyi' | 'orta' | 'kotu';

export interface SeoBulgu {
  kod: string;
  seviye: Seviye;
  bolum: string | null;
  deger?: number | string;
  kritik?: boolean;
}

export interface SeoOlcumKisa {
  id: number;
  olcum_at: string | null;
  kaynak: 'zamanli' | 'elle' | 'yonetici' | string;
  durum: 'tamam' | 'hata' | 'calisiyor' | string;
  hata_kodu: string | null;
  genel_puan: number | null;
  mobil_puan: number | null;
  masaustu_puan: number | null;
  lcp_ms: number | null;
  cls: number | null;
  tbt_ms: number | null;
}

export interface SeoOlcum extends SeoOlcumKisa {
  bolum_puanlari: Record<string, number | null>;
  onemli_bulgular: SeoBulgu[];
  kritik: string[];
  kirik_baglanti: number;
  bulgu_sayisi: Record<'hata' | 'uyari' | 'bilgi', number>;
}

export interface SeoGecmisi {
  site_id: number;
  ad: string;
  adres: string | null;
  tarama_gun: number;
  gun: number;
  son: SeoOlcum | null;
  onceki_puan: number | null;
  degisim: number | null;
  son_deneme: SeoOlcumKisa | null;
  calisiyor: boolean;
  sonraki_tarama_at: string | null;
  gecmis: SeoOlcumKisa[];
  elle: { kalan: number | null; sonraki_at: string | null; sinirsiz: boolean };
}

export interface SeoOzetSatiri {
  site_id: number;
  ad: string;
  adres: string | null;
  client_email: string;
  tarama_gun: number;
  son: SeoOlcumKisa | null;
  onceki_puan: number | null;
  degisim: number | null;
  kritik: string[];
  yeni_kritik: string[];
  dususte: boolean;
  son_deneme: SeoOlcumKisa | null;
  calisiyor: boolean;
  sonraki_tarama_at: string | null;
}

/** Uçtan dönen hata; `kod` sunucunun `detail.kod`u (ör. `gunluk_sinir`). */
export class SeoHatasi extends Error {
  durum: number;
  kod: string;
  ek: Record<string, unknown>;

  constructor(durum: number, kod: string, ek: Record<string, unknown> = {}) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
    this.ek = ek;
  }
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    const durum = h?.response?.status ?? h?.status ?? 0;
    const detay = h?.response?.data?.detail;
    if (detay && typeof detay === 'object' && 'kod' in (detay as Record<string, unknown>)) {
      const d = detay as Record<string, unknown>;
      throw new SeoHatasi(durum, String(d.kod), d);
    }
    throw new SeoHatasi(durum, typeof detay === 'string' ? detay : 'genel');
  }
}

// --- Müşteri -----------------------------------------------------------------
export function musteriSeoGecmisi(siteId: number, gun = 90): Promise<SeoGecmisi> {
  return istek<SeoGecmisi>('GET', `/api/v1/sitelerim/${siteId}/seo-gecmisi?gun=${gun}`);
}

export function musteriSeoTara(siteId: number): Promise<{ olcum: SeoOlcum; uyari_sayisi: number }> {
  return istek('POST', `/api/v1/sitelerim/${siteId}/seo-tara`);
}

// --- Yönetici ----------------------------------------------------------------
export async function seoOzeti(): Promise<{ siteler: SeoOzetSatiri[]; esik: number }> {
  const g = await istek<{ siteler: SeoOzetSatiri[]; esik: number }>('GET', '/api/v1/site-bakim/seo-ozet');
  return { siteler: Array.isArray(g?.siteler) ? g.siteler : [], esik: g?.esik ?? 10 };
}

export function yoneticiSeoGecmisi(siteId: number, gun = 90): Promise<SeoGecmisi> {
  return istek<SeoGecmisi>('GET', `/api/v1/site-bakim/${siteId}/seo-gecmisi?gun=${gun}`);
}

export function yoneticiSeoTara(siteId: number): Promise<{ olcum: SeoOlcum; uyari_sayisi: number }> {
  return istek('POST', `/api/v1/site-bakim/${siteId}/seo-tara`);
}

export function seoAyarKaydet(siteId: number, taramaGun: number): Promise<{ site_id: number; tarama_gun: number }> {
  return istek('PUT', `/api/v1/site-bakim/${siteId}/seo-ayar`, { tarama_gun: taramaGun });
}

// --- Biçim ve eşikler ----------------------------------------------------------
/** Google Core Web Vitals eşikleri (iyi ≤ ilk, orta ≤ ikinci). */
export const CWV_ESIKLERI = {
  lcp: [2500, 4000],
  cls: [0.1, 0.25],
  tbt: [200, 600],
} as const;

export function cwvDurumu(metrik: keyof typeof CWV_ESIKLERI, deger: number | null | undefined): CwvDurumu | null {
  if (deger === null || deger === undefined) return null;
  const [iyi, orta] = CWV_ESIKLERI[metrik];
  if (deger <= iyi) return 'iyi';
  if (deger <= orta) return 'orta';
  return 'kotu';
}

export const CWV_RENGI: Record<CwvDurumu, string> = {
  iyi: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-300',
  orta: 'border-amber-400/40 bg-amber-500/10 text-amber-300',
  kotu: 'border-red-400/40 bg-red-500/10 text-red-300',
};

/** Lighthouse renkleri: ≥90 yeşil, ≥50 sarı, altı kırmızı. */
export function puanRengi(puan: number | null | undefined): string {
  if (puan === null || puan === undefined) return 'text-muted-foreground';
  if (puan >= 90) return 'text-emerald-300';
  if (puan >= 50) return 'text-amber-300';
  return 'text-red-300';
}

export function sureBicimle(ms: number | null | undefined, dil: string): string {
  if (ms === null || ms === undefined) return '—';
  try {
    return ms >= 1000
      ? new Intl.NumberFormat(dil, { style: 'unit', unit: 'second', maximumFractionDigits: 1 }).format(ms / 1000)
      : new Intl.NumberFormat(dil, { style: 'unit', unit: 'millisecond', maximumFractionDigits: 0 }).format(ms);
  } catch {
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
  }
}

export function sayiBicimle(deger: number | null | undefined, dil: string, basamak = 2): string {
  if (deger === null || deger === undefined) return '—';
  try {
    return new Intl.NumberFormat(dil, { maximumFractionDigits: basamak }).format(deger);
  } catch {
    return String(deger);
  }
}

export function tarihBicimle(deger: string | null | undefined, dil: string, saatli = false): string {
  if (!deger) return '—';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '—';
  try {
    return saatli
      ? an.toLocaleString(dil, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      : an.toLocaleDateString(dil, { year: 'numeric', month: 'short', day: '2-digit' });
  } catch {
    return an.toISOString().slice(0, saatli ? 16 : 10);
  }
}
