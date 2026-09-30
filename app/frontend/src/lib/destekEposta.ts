import { client } from '@/lib/sdkClient';

/**
 * Faz 2F — E-postadan destek talebi ve otomatik destek kuralları.
 *
 * Yönetici  /api/v1/destek/eposta-ayarlari, /gelen-epostalar
 *           /api/v1/destek/kurallar (+ /sirala, /dene, /{id})
 * Oturum    /api/v1/destek/eposta-bilgisi (müşteri ipucu)
 */

export type KosulAlani = 'konu' | 'metin' | 'konu_veya_metin' | 'gonderen' | 'kanal' | 'oncelik' | 'hizmet' | 'paket';
export type EylemTuru = 'oncelik' | 'ata' | 'hizmet' | 'etiket' | 'hazir_cevap' | 'durdur';

export interface Kosul {
  alan: KosulAlani;
  islec: string;
  deger: string;
}

export interface Eylem {
  tur: EylemTuru;
  deger?: string | number;
}

export interface Kural {
  id: number;
  ad: string;
  aktif: boolean;
  sira: number;
  eslesme: 'hepsi' | 'herhangi';
  kosullar: Kosul[];
  eylemler: Eylem[];
}

export type KuralGirdisi = Omit<Kural, 'id' | 'sira'>;

export interface DeneSonucu {
  eslesen: { id: number; ad: string; eylemler: Eylem[] }[];
  durduruldu: boolean;
  paket: string | null;
}

export interface EpostaAyarlari {
  genel_anahtar_tanimli: boolean;
  resend_imza_tanimli: boolean;
  resend_api_tanimli: boolean;
  gelen_adres: string;
  webhook: { genel: string; resend: string };
  sinirlar: { saatlik: number; ek_mb: number; ek_sayisi: number };
}

export interface GelenEposta {
  id: number;
  gonderen: string | null;
  konu: string | null;
  durum: 'isleniyor' | 'islendi' | 'yoksayildi' | 'hata';
  neden: string | null;
  talep_id: number | null;
  kaynak: string | null;
  ozet: string | null;
  ek_sayisi: number;
  created_at: string | null;
}

/** Koşul alanı → izinli işleçler (arka uçtaki listeyle aynı). */
export const KOSUL_ISLECLERI: Record<KosulAlani, string[]> = {
  konu: ['icerir', 'icermez', 'esittir'],
  metin: ['icerir', 'icermez', 'esittir'],
  konu_veya_metin: ['icerir', 'icermez', 'esittir'],
  gonderen: ['esittir', 'alan_adi', 'icerir'],
  kanal: ['esittir', 'esit_degil'],
  oncelik: ['esittir', 'esit_degil'],
  hizmet: ['esittir', 'esit_degil'],
  paket: ['esittir', 'esit_degil'],
};

export const EYLEM_TURLERI: EylemTuru[] = ['oncelik', 'ata', 'hizmet', 'etiket', 'hazir_cevap', 'durdur'];

export class EpostaHatasi extends Error {
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

async function istek<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> | undefined });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    const detay = h?.response?.data?.detail as { kod?: unknown } | undefined;
    throw new EpostaHatasi(
      h?.response?.status ?? h?.status ?? 0,
      detay && typeof detay === 'object' && typeof detay.kod === 'string' ? detay.kod : 'genel'
    );
  }
}

// --- E-postadan talep ------------------------------------------------------
export const epostaAyarlari = () => istek<EpostaAyarlari>('GET', '/api/v1/destek/eposta-ayarlari');
export const epostaAyarlariKaydet = (gelen_adres: string) =>
  istek<EpostaAyarlari>('PUT', '/api/v1/destek/eposta-ayarlari', { gelen_adres });

export async function gelenEpostalar(durum?: string): Promise<GelenEposta[]> {
  const q = durum ? `?durum=${encodeURIComponent(durum)}` : '';
  const g = await istek<GelenEposta[]>('GET', `/api/v1/destek/gelen-epostalar${q}`);
  return Array.isArray(g) ? g : [];
}

export const epostaBilgisi = () => istek<{ acik: boolean; gelen_adres: string }>('GET', '/api/v1/destek/eposta-bilgisi');

// --- Kurallar ------------------------------------------------------------------
export async function kurallar(): Promise<Kural[]> {
  const g = await istek<Kural[]>('GET', '/api/v1/destek/kurallar');
  return Array.isArray(g) ? g : [];
}

export const kuralEkle = (k: KuralGirdisi) => istek<Kural>('POST', '/api/v1/destek/kurallar', k);
export const kuralGuncelle = (id: number, k: KuralGirdisi) => istek<Kural>('PUT', `/api/v1/destek/kurallar/${id}`, k);
export const kuralSil = (id: number) => istek<{ silindi: number }>('DELETE', `/api/v1/destek/kurallar/${id}`);
export const kurallariSirala = (idler: number[]) => istek<Kural[]>('POST', '/api/v1/destek/kurallar/sirala', { idler });
export const kurallariDene = (g: { konu: string; metin: string; gonderen: string; kanal: string }) =>
  istek<DeneSonucu>('POST', '/api/v1/destek/kurallar/dene', g);
