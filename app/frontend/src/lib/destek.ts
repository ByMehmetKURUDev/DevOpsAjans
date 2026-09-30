import { client } from '@/lib/sdkClient';

/**
 * Faz 2C — Destek: SLA durumları/ayarları, hazır cevaplar, bilgi bankası.
 *
 * Yönetici  /api/v1/destek/sla, /sla-ayarlari, /hazir-cevaplar
 *           /api/v1/bilgi-bankasi/yonetim
 * Müşteri   /api/v1/destek/sla-bilgisi
 *           /api/v1/bilgi-bankasi?q=&dil=, /oneri?baslik=, /<id>
 */

export type HedefDurumu = 'yok' | 'zamaninda' | 'yaklasiyor' | 'asildi' | 'karsilandi' | 'gecikti';
export type Oncelik = 'acil' | 'yuksek' | 'normal' | 'dusuk';

export interface HedefBilgisi {
  durum: HedefDurumu;
  hedef: string | null;
  kalan_dk: number | null;
  tamam?: string;
}

export interface SlaDurumu {
  ticket_id: number;
  oncelik: Oncelik;
  ilk_yanit: HedefBilgisi;
  cozum: HedefBilgisi;
  ozet: HedefDurumu;
}

export interface SlaAyarlari {
  mesai: { bas: string; bit: string; gunler: number[] };
  tatiller: string[];
  hedefler: Record<Oncelik, { ilk_yanit_dk: number; cozum_dk: number }>;
}

export interface SlaBilgisi {
  mesai: SlaAyarlari['mesai'];
  hedefler: SlaAyarlari['hedefler'];
  talepler: Record<string, { oncelik: Oncelik; ilk_yanit_hedef: string | null; ilk_yanit_durum: HedefDurumu }>;
}

export interface HazirCevap {
  id: number;
  baslik: string;
  metin: string;
}

export interface MakaleOzeti {
  id: number;
  kategori: string | null;
  baslik: string;
  ozet: string;
  dil: string;
}

export interface Makale {
  id: number;
  kategori: string | null;
  baslik: string;
  html: string;
  dil: string;
}

export interface YonetimMakalesi {
  id: number;
  kategori: string | null;
  baslik: string;
  icerik: string;
  ceviriler: Record<string, { baslik: string; icerik: string }>;
  durum: 'taslak' | 'yayinda';
  goruntulenme: number;
  updated_at: string | null;
}

export class DestekHatasi extends Error {
  durum: number;
  kod: string;

  constructor(durum: number, kod: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
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
    const detay = h?.response?.data?.detail as { kod?: unknown } | undefined;
    throw new DestekHatasi(
      h?.response?.status ?? h?.status ?? 0,
      detay && typeof detay === 'object' && typeof detay.kod === 'string' ? detay.kod : 'genel'
    );
  }
}

// --- SLA -------------------------------------------------------------------
export async function slaDurumlari(ids: number[]): Promise<Record<string, SlaDurumu>> {
  if (!ids.length) return {};
  const g = await istek<Record<string, SlaDurumu>>('GET', `/api/v1/destek/sla?ids=${ids.slice(0, 500).join(',')}`);
  return g && typeof g === 'object' ? g : {};
}

export const slaAyarlari = () => istek<SlaAyarlari>('GET', '/api/v1/destek/sla-ayarlari');
export const slaAyarlariKaydet = (a: SlaAyarlari) =>
  istek<SlaAyarlari>('PUT', '/api/v1/destek/sla-ayarlari', a as unknown as Record<string, unknown>);
export const slaBilgisi = () => istek<SlaBilgisi>('GET', '/api/v1/destek/sla-bilgisi');

// --- Hazır cevaplar -----------------------------------------------------------
export async function hazirCevaplar(): Promise<HazirCevap[]> {
  const g = await istek<HazirCevap[]>('GET', '/api/v1/destek/hazir-cevaplar');
  return Array.isArray(g) ? g : [];
}
export const hazirCevapEkle = (baslik: string, metin: string) =>
  istek<HazirCevap>('POST', '/api/v1/destek/hazir-cevaplar', { baslik, metin });
export const hazirCevapGuncelle = (id: number, baslik: string, metin: string) =>
  istek<HazirCevap>('PUT', `/api/v1/destek/hazir-cevaplar/${id}`, { baslik, metin });
export const hazirCevapSil = (id: number) => istek<{ silindi: number }>('DELETE', `/api/v1/destek/hazir-cevaplar/${id}`);
export const hazirCevapUygula = (id: number, ticketId: number) =>
  istek<{ metin: string }>('POST', `/api/v1/destek/hazir-cevaplar/${id}/uygula`, { ticket_id: ticketId });

// --- Bilgi bankası ------------------------------------------------------------
export async function makaleAra(q: string, dil: string): Promise<MakaleOzeti[]> {
  const g = await istek<{ makaleler: MakaleOzeti[] }>(
    'GET',
    `/api/v1/bilgi-bankasi?q=${encodeURIComponent(q)}&dil=${encodeURIComponent(dil)}`
  );
  return g?.makaleler ?? [];
}

export async function makaleOnerisi(baslik: string, dil: string): Promise<MakaleOzeti[]> {
  const g = await istek<{ makaleler: MakaleOzeti[] }>(
    'GET',
    `/api/v1/bilgi-bankasi/oneri?baslik=${encodeURIComponent(baslik)}&dil=${encodeURIComponent(dil)}`
  );
  return g?.makaleler ?? [];
}

export const makaleGetir = (id: number, dil: string) =>
  istek<Makale>('GET', `/api/v1/bilgi-bankasi/${id}?dil=${encodeURIComponent(dil)}`);

export async function yonetimMakaleleri(): Promise<YonetimMakalesi[]> {
  const g = await istek<YonetimMakalesi[]>('GET', '/api/v1/bilgi-bankasi/yonetim');
  return Array.isArray(g) ? g : [];
}

export type MakaleGirdisi = Omit<YonetimMakalesi, 'id' | 'goruntulenme' | 'updated_at'>;

export const makaleEkle = (m: MakaleGirdisi) =>
  istek<YonetimMakalesi>('POST', '/api/v1/bilgi-bankasi/yonetim', m as unknown as Record<string, unknown>);
export const makaleGuncelle = (id: number, m: MakaleGirdisi) =>
  istek<YonetimMakalesi>('PUT', `/api/v1/bilgi-bankasi/yonetim/${id}`, m as unknown as Record<string, unknown>);
export const makaleSil = (id: number) => istek<{ silindi: number }>('DELETE', `/api/v1/bilgi-bankasi/yonetim/${id}`);
export const makaleOnizle = (icerik: string) =>
  istek<{ html: string }>('POST', '/api/v1/bilgi-bankasi/yonetim/onizle', { icerik });
