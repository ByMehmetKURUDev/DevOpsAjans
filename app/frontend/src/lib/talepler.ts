import { client } from '@/lib/sdkClient';

/**
 * Talep yazışması.
 *
 * `support_tickets` kaydı talebin kendisi; buradaki uçlar onun
 * altındaki mesajları taşıyor. Mesajı kimin yazdığı sunucuda
 * oturumdan belirleniyor, buradan gönderilmiyor.
 */

export type Yazan = 'musteri' | 'ajans';

export interface TalepMesaji {
  id: number;
  ticket_id: number;
  yazan: Yazan;
  yazan_ad?: string | null;
  mesaj: string;
  created_at?: string | null;
}

export interface TalepYazismasi {
  ticket_id: number;
  subject: string;
  hizmet?: string | null;
  durum?: string | null;
  mesajlar: TalepMesaji[];
}

/**
 * Hizmet anahtarları. Başlıkları dil dosyalarında
 * (`talep.hizmetler.<anahtar>`); sıralama müşteri panelindeki düğme
 * sırası.
 *
 * Arka uçta da aynı liste var ve kaydı o doğruluyor. Buradaki kopya
 * yalnızca düğmeleri çizmek için: ağ isteği beklemeden panel açılsın.
 */
export const HIZMETLER = [
  'website',
  'seo',
  'google_ads',
  'sosyal_ads',
  'sosyal_pr',
  'sosyal_tasarim',
  'youtube_pr',
  'youtube_gelistirme',
  'youtube_otomasyon',
  'basin_pr',
  'yeni_ozellik',
  'genel',
] as const;

export type Hizmet = (typeof HIZMETLER)[number];

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

export async function yazismayiGetir(ticketId: number): Promise<TalepYazismasi> {
  const yanit = await client.apiCall.invoke({
    method: 'GET',
    url: `/api/v1/talep/${ticketId}/mesajlar`,
  });
  const govde = govdeyiAc<Partial<TalepYazismasi>>(yanit);
  if (!govde || typeof govde.ticket_id !== 'number') {
    throw new Error('Yazışma alınamadı.');
  }
  return {
    ticket_id: govde.ticket_id,
    subject: govde.subject || '',
    hizmet: govde.hizmet ?? null,
    durum: govde.durum ?? null,
    mesajlar: Array.isArray(govde.mesajlar) ? govde.mesajlar : [],
  };
}

export async function mesajGonder(ticketId: number, mesaj: string): Promise<TalepMesaji> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: `/api/v1/talep/${ticketId}/mesaj`,
    data: { mesaj },
  });
  const govde = govdeyiAc<TalepMesaji>(yanit);
  if (!govde?.mesaj) throw new Error('Mesaj gönderilemedi.');
  return govde;
}
