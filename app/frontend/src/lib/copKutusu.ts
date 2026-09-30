import { client } from '@/lib/sdkClient';

/**
 * Faz 2D — çöp kutusu uçları.
 *
 * Silinen kayıtların (proje, görev, dosya, destek talebi, fatura, blog…)
 * tam kopyası saklama süresi boyunca (varsayılan 30 gün) duruyor. Yönetici
 * her şeyi görür, geri alır, kalıcı siler; müşteri yalnız kendi sildiği
 * kendi kayıtlarını görür ve geri alır.
 */

export interface CopSatiri {
  id: number;
  tablo: string;
  kayit_id?: string | null;
  etiket?: string | null;
  silen_email?: string | null;
  silen_rol?: string | null;
  sahip_email?: string | null;
  silinme?: string | null;
  geri_alindi: boolean;
  geri_alan?: string | null;
  geri_alinma?: string | null;
  bagli_sayisi: number;
  kalici_silinme?: string | null;
}

export interface CopListesi {
  items: CopSatiri[];
  toplam: number;
  sayfa: number;
  adet: number;
  saklama_gun: number;
  tablolar: string[];
}

export interface CopAyrintisi extends CopSatiri {
  veri: Record<string, unknown>;
}

export class CopHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string
  ) {
    super(kod);
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
    throw new CopHatasi(
      h?.response?.status ?? h?.status ?? 0,
      detay && typeof detay === 'object' && typeof detay.kod === 'string' ? detay.kod : 'genel'
    );
  }
}

function listeyiDuzelt(g: Partial<CopListesi> | undefined, sayfa: number, adet: number): CopListesi {
  return {
    items: Array.isArray(g?.items) ? g!.items : [],
    toplam: g?.toplam ?? 0,
    sayfa: g?.sayfa ?? sayfa,
    adet: g?.adet ?? adet,
    saklama_gun: g?.saklama_gun ?? 30,
    tablolar: Array.isArray(g?.tablolar) ? g!.tablolar : [],
  };
}

function sorguKur(filtre: { tablo?: string; q?: string }, sayfa: number, adet: number) {
  const sorgu = new URLSearchParams({ sayfa: String(sayfa), adet: String(adet) });
  if (filtre.tablo) sorgu.set('tablo', filtre.tablo);
  if (filtre.q?.trim()) sorgu.set('q', filtre.q.trim());
  return sorgu;
}

// --- Yönetici -----------------------------------------------------------------
export async function copListesi(filtre: { tablo?: string; q?: string }, sayfa = 1, adet = 50): Promise<CopListesi> {
  const g = await istek<Partial<CopListesi>>('GET', `/api/v1/cop-kutusu?${sorguKur(filtre, sayfa, adet)}`);
  return listeyiDuzelt(g, sayfa, adet);
}

export async function copAyrintisi(id: number): Promise<CopAyrintisi> {
  return istek('GET', `/api/v1/cop-kutusu/${id}`);
}

export async function copGeriAl(id: number): Promise<{ geri_alinan: { id: number; tablo: string }[] }> {
  return istek('POST', `/api/v1/cop-kutusu/${id}/geri-al`);
}

export async function copKaliciSil(id: number): Promise<void> {
  await istek('DELETE', `/api/v1/cop-kutusu/${id}`);
}

export async function copSaklamaAyari(gun: number): Promise<{ saklama_gun: number }> {
  return istek('PUT', '/api/v1/cop-kutusu/ayar', { gun });
}

// --- Müşteri ------------------------------------------------------------------
export async function silinenlerim(sayfa = 1, adet = 50): Promise<CopListesi> {
  const g = await istek<Partial<CopListesi>>('GET', `/api/v1/cop-kutum?${sorguKur({}, sayfa, adet)}`);
  return listeyiDuzelt(g, sayfa, adet);
}

export async function silineniGeriAl(id: number): Promise<{ geri_alinan: { id: number; tablo: string }[] }> {
  return istek('POST', `/api/v1/cop-kutum/${id}/geri-al`);
}

/** Hata kodunu (`{"detail": {"kod"}}`) çevrili metne çevirir. */
export function copHataMetni(t: (k: string, o?: Record<string, unknown>) => string, hata: unknown): string {
  const kod = hata instanceof CopHatasi ? hata.kod : 'genel';
  return t(`copKutusu.hataKod.${kod}`, { defaultValue: t('copKutusu.hataKod.genel') });
}
