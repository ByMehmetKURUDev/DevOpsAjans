import { client } from '@/lib/sdkClient';

/**
 * Müşteri siteleri, bakım erişimi ve gömülü geri bildirim düğmesi.
 *
 * Müşterinin şifresi hiçbir yerde tutulmuyor. Bakım için ajansın
 * kendi hesabı açılıyor, yapılan her iş erişim günlüğüne yazılıyor,
 * müşteri izni tek düğmeyle geri alabiliyor.
 */

export type SitePlatformu = 'wordpress' | 'custom' | 'shopify' | 'wix' | 'webflow' | 'diger';
export type SiteDurumu = 'aktif' | 'beklemede' | 'bitti';

export const PLATFORMLAR: { anahtar: SitePlatformu; etiket: string }[] = [
  { anahtar: 'wordpress', etiket: 'WordPress' },
  { anahtar: 'custom', etiket: 'Özel kod' },
  { anahtar: 'shopify', etiket: 'Shopify' },
  { anahtar: 'wix', etiket: 'Wix' },
  { anahtar: 'webflow', etiket: 'Webflow' },
  { anahtar: 'diger', etiket: 'Diğer' },
];

export const ISLEMLER = [
  'giris',
  'guncelleme',
  'yedek',
  'eklenti',
  'duzeltme',
] as const;

export type Islem = (typeof ISLEMLER)[number] | 'izin_acildi' | 'izin_kapandi';

export interface MusteriSitesi {
  id: number;
  client_email: string;
  ad: string;
  adres?: string | null;
  platform?: SitePlatformu | null;
  durum?: SiteDurumu | null;
  bakim_izni?: boolean | null;
  izin_at?: string | null;
  izin_notu?: string | null;
  widget_acik?: boolean | null;
  atanan?: string | null;
}

export interface GunlukSatiri {
  id: number;
  site_id?: number | null;
  site_ad?: string | null;
  kim: string;
  islem: Islem;
  aciklama?: string | null;
  created_at?: string | null;
}

export interface GommeKodu {
  kod: string;
  jeton: string;
  acik?: boolean;
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

// --------------------------------------------------------------------------
// Yönetici / ekip
// --------------------------------------------------------------------------
export async function siteleriGetir(): Promise<MusteriSitesi[]> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/musteri-sitesi' });
  const govde = govdeyiAc<MusteriSitesi[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}

export async function siteEkle(girdi: {
  client_email: string;
  ad: string;
  adres?: string;
  platform?: SitePlatformu;
  atanan?: string;
}): Promise<MusteriSitesi> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/musteri-sitesi',
    data: girdi,
  });
  const govde = govdeyiAc<MusteriSitesi>(yanit);
  if (!govde?.id) throw new Error('Site eklenemedi.');
  return govde;
}

export async function siteGuncelle(
  id: number,
  degisiklik: Partial<Pick<MusteriSitesi, 'ad' | 'adres' | 'platform' | 'durum' | 'atanan' | 'widget_acik'>>,
): Promise<MusteriSitesi> {
  const yanit = await client.apiCall.invoke({
    method: 'PATCH',
    url: `/api/v1/musteri-sitesi/${id}`,
    data: degisiklik,
  });
  const govde = govdeyiAc<MusteriSitesi>(yanit);
  if (!govde?.id) throw new Error('Site güncellenemedi.');
  return govde;
}

export async function siteSil(id: number): Promise<void> {
  await client.apiCall.invoke({ method: 'DELETE', url: `/api/v1/musteri-sitesi/${id}` });
}

export async function gommeKoduGetir(id: number): Promise<GommeKodu> {
  const yanit = await client.apiCall.invoke({
    method: 'GET',
    url: `/api/v1/musteri-sitesi/${id}/gomme`,
  });
  const govde = govdeyiAc<GommeKodu>(yanit);
  if (!govde?.kod) throw new Error('Gömme kodu alınamadı.');
  return govde;
}

export async function jetonYenile(id: number): Promise<GommeKodu> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: `/api/v1/musteri-sitesi/${id}/jeton`,
  });
  const govde = govdeyiAc<GommeKodu>(yanit);
  if (!govde?.kod) throw new Error('Jeton yenilenemedi.');
  return govde;
}

export async function erisimKaydet(
  id: number,
  islem: string,
  aciklama?: string,
): Promise<GunlukSatiri> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: `/api/v1/musteri-sitesi/${id}/erisim`,
    data: { islem, aciklama },
  });
  const govde = govdeyiAc<GunlukSatiri>(yanit);
  if (!govde?.id) throw new Error('Erişim kaydedilemedi.');
  return govde;
}

export async function siteGunluguGetir(id: number): Promise<GunlukSatiri[]> {
  const yanit = await client.apiCall.invoke({
    method: 'GET',
    url: `/api/v1/musteri-sitesi/${id}/gunluk`,
  });
  const govde = govdeyiAc<GunlukSatiri[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}

// --------------------------------------------------------------------------
// Müşteri
// --------------------------------------------------------------------------
export async function kendiSitelerim(): Promise<MusteriSitesi[]> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/sitelerim' });
  const govde = govdeyiAc<MusteriSitesi[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}

export async function bakimIzni(
  id: number,
  izin: boolean,
  not?: string,
): Promise<MusteriSitesi> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: `/api/v1/sitelerim/${id}/izin`,
    data: { izin, not_: not },
  });
  const govde = govdeyiAc<MusteriSitesi>(yanit);
  if (!govde?.id) throw new Error('İzin değiştirilemedi.');
  return govde;
}

export async function kendiGunlugum(id: number): Promise<GunlukSatiri[]> {
  const yanit = await client.apiCall.invoke({
    method: 'GET',
    url: `/api/v1/sitelerim/${id}/gunluk`,
  });
  const govde = govdeyiAc<GunlukSatiri[]>(yanit);
  return Array.isArray(govde) ? govde : [];
}
