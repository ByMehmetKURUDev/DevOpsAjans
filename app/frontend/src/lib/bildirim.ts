import { client } from '@/lib/sdkClient';

/**
 * Bildirim tercihleri (kişisel) ve olay × kanal matrisi (yönetici).
 *
 * Kural sunucuda: yönetici matrisi izin vermiyorsa kişi açamaz, izin
 * veriyorsa kişi kapatabilir; panel içi (inapp) kapatılamaz.
 */

export const KANALLAR = ['inapp', 'email', 'push', 'sms', 'whatsapp'] as const;
export type Kanal = (typeof KANALLAR)[number];
export type KanalDurumu = 'hazir' | 'kapali' | 'yapilandirilmadi';
export type Rol = 'admin' | 'client';
export type Hucre = Record<Kanal, boolean>;
export type Matris = Record<Rol, Record<string, Hucre>>;

export interface SessizSaatler {
  bas: string;
  bit: string;
}

export interface PushBilgisi {
  yapilandirildi: boolean;
  anahtar: string | null;
  abonelik_sayisi: number;
  kisi_sayisi?: number;
}

export interface TercihOlayi {
  olay: string;
  /** Yönetici matrisinin izni. */
  izin: Hucre;
  /** Etkin durum: izin ve kişinin kapatmadığı. */
  acik: Hucre;
}

export interface Tercihlerim {
  rol: Rol;
  kanallar: Kanal[];
  kanal_durumu: Record<Kanal, KanalDurumu>;
  olaylar: TercihOlayi[];
  sessiz_saatler: SessizSaatler | null;
  push: PushBilgisi;
}

export interface MatrisOlayi {
  olay: string;
  roller: Rol[];
  tetikleniyor: boolean;
}

export interface MatrisYaniti {
  matris: Matris;
  kanallar: Kanal[];
  olaylar: MatrisOlayi[];
  kanal_durumu: Record<Kanal, KanalDurumu>;
  push: PushBilgisi;
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

function zorunlu<T>(deger: T | undefined): T {
  if (!deger) throw new Error('Sunucudan yanıt alınamadı');
  return deger;
}

export async function tercihlerimiGetir(): Promise<Tercihlerim> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/bildirim/tercihlerim' });
  return zorunlu(govdeyiAc<Tercihlerim>(yanit));
}

export async function tercihlerimiKaydet(
  tercih: Record<string, Partial<Hucre>>,
  sessiz_saatler: SessizSaatler | null
): Promise<Tercihlerim> {
  const yanit = await client.apiCall.invoke({
    method: 'PUT',
    url: '/api/v1/bildirim/tercihlerim',
    data: { tercih, sessiz_saatler },
  });
  return zorunlu(govdeyiAc<Tercihlerim>(yanit));
}

export async function matrisiGetir(): Promise<MatrisYaniti> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/bildirim/matris' });
  return zorunlu(govdeyiAc<MatrisYaniti>(yanit));
}

export async function matrisiKaydet(matris: Matris): Promise<MatrisYaniti> {
  const yanit = await client.apiCall.invoke({ method: 'PUT', url: '/api/v1/bildirim/matris', data: { matris } });
  return zorunlu(govdeyiAc<MatrisYaniti>(yanit));
}
