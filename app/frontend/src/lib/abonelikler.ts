import { client } from '@/lib/sdkClient';

/**
 * Hizmet abonelikleri ve aylık raporlar.
 *
 * Fatura tek seferlik bir tutar; abonelik "her ay şu iş yapılıyor"
 * demek. Rapor taslakken müşteri panelinde görünmüyor.
 */

export type AbonelikDurumu = 'aktif' | 'duraklatildi' | 'iptal';
export type RaporDurumu = 'taslak' | 'yayinlandi';

export interface Abonelik {
  id: number;
  client_email: string;
  client_name?: string | null;
  hizmet: string;
  baslik?: string | null;
  tutar?: number | null;
  para_birimi?: string | null;
  periyot?: string | null;
  durum?: AbonelikDurumu | null;
  baslangic?: string | null;
  sonraki_rapor?: string | null;
  notlar?: string | null;
}

export interface Rapor {
  id: number;
  subscription_id?: number | null;
  client_email: string;
  hizmet?: string | null;
  donem: string;
  baslik?: string | null;
  ozet?: string | null;
  metrikler?: Record<string, unknown> | null;
  durum?: RaporDurumu | null;
  yayin_at?: string | null;
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

export async function abonelikleriGetir(): Promise<Abonelik[]> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/abonelik' });
  const govde = govdeyiAc<Abonelik[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}

export async function abonelikEkle(girdi: {
  client_email: string;
  client_name?: string;
  hizmet: string;
  baslik?: string;
  tutar?: number;
  para_birimi?: string;
  periyot?: 'aylik' | 'yillik';
}): Promise<Abonelik> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/abonelik',
    data: girdi,
  });
  const govde = govdeyiAc<Abonelik>(yanit);
  if (!govde?.id) throw new Error('Abonelik eklenemedi.');
  return govde;
}

export async function abonelikDurumu(id: number, durum: AbonelikDurumu): Promise<void> {
  await client.apiCall.invoke({
    method: 'POST',
    url: `/api/v1/abonelik/${id}/durum`,
    data: { durum },
  });
}

export async function abonelikSil(id: number): Promise<void> {
  await client.apiCall.invoke({ method: 'DELETE', url: `/api/v1/abonelik/${id}` });
}

export async function raporlariGetir(): Promise<Rapor[]> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/abonelik/raporlar' });
  const govde = govdeyiAc<Rapor[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}

export async function raporYaz(girdi: {
  subscription_id: number;
  donem?: string;
  baslik?: string;
  ozet?: string;
  metrikler?: Record<string, unknown>;
}): Promise<Rapor> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/abonelik/raporlar',
    data: girdi,
  });
  const govde = govdeyiAc<Rapor>(yanit);
  if (!govde?.id) throw new Error('Rapor kaydedilemedi.');
  return govde;
}

export async function raporYayimla(id: number): Promise<void> {
  await client.apiCall.invoke({
    method: 'POST',
    url: `/api/v1/abonelik/raporlar/${id}/yayimla`,
    data: {},
  });
}

export async function raporSil(id: number): Promise<void> {
  await client.apiCall.invoke({ method: 'DELETE', url: `/api/v1/abonelik/raporlar/${id}` });
}

/** Müşterinin kendi yayınlanmış raporları. */
export async function kendiRaporlarim(): Promise<Rapor[]> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/raporlarim' });
  const govde = govdeyiAc<Rapor[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}
