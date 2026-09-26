import { client } from '@/lib/sdkClient';

/**
 * Ekip, talep atama ve müşteri raporları.
 *
 * `staff` bir yetki tablosu değil, ekip listesi. Yöneticiliği hâlâ
 * kullanıcı hesabının rolü belirliyor; buradaki kayıt kişiye talep
 * atanabilmesini ve atandığı talebi görebilmesini sağlıyor.
 */

export type PersonelRolu = 'yonetici' | 'calisan';

export interface Personel {
  id: number;
  ad: string;
  email: string;
  rol?: PersonelRolu | null;
  hizmetler?: string | null;
  aktif?: boolean | null;
}

export interface MusteriRaporu {
  client_email: string;
  client_name?: string | null;
  toplam: number;
  acik: number;
  cevaplanan: number;
  kapali: number;
  hizmetler: Record<string, number>;
  son_hareket?: string | null;
}

export interface RaporOzeti {
  musteri_sayisi: number;
  toplam_talep: number;
  acik_talep: number;
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

export async function ekibiGetir(): Promise<Personel[]> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/ekip' });
  const govde = govdeyiAc<Personel[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}

export async function personelEkle(girdi: {
  ad: string;
  email: string;
  rol: PersonelRolu;
  hizmetler?: string;
}): Promise<Personel> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/ekip',
    data: { ...girdi, aktif: true },
  });
  const govde = govdeyiAc<Personel>(yanit);
  if (!govde?.id) throw new Error('Kişi eklenemedi.');
  return govde;
}

export async function personelSil(id: number): Promise<void> {
  await client.apiCall.invoke({ method: 'DELETE', url: `/api/v1/ekip/${id}` });
}

/** Boş e-posta ataması kaldırıyor. */
export async function talebiAta(ticketId: number, email: string | null): Promise<void> {
  await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/ekip/ata',
    data: { ticket_id: ticketId, email: email || null },
  });
}

export async function musteriRaporlariniGetir(): Promise<{
  musteriler: MusteriRaporu[];
  ozet: RaporOzeti;
}> {
  const yanit = await client.apiCall.invoke({
    method: 'GET',
    url: '/api/v1/ekip/musteri-raporlari',
  });
  const govde = govdeyiAc<{ musteriler: MusteriRaporu[]; ozet: RaporOzeti }>(yanit);
  return {
    musteriler: Array.isArray(govde?.musteriler) ? govde!.musteriler : [],
    ozet: govde?.ozet ?? { musteri_sayisi: 0, toplam_talep: 0, acik_talep: 0 },
  };
}
