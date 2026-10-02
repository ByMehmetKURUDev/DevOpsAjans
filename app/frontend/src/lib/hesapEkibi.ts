import { client } from '@/lib/sdkClient';
import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 2E — hesap ekibi uçları (üyeler, davet, hesaplarım).
 *
 * Hesap = sahibinin e-postası. Ekip üyesi kendi e-postasıyla giriş yapar,
 * hangi hesapta çalıştığını `X-MK-Hesap` başlığıyla söyler (bkz.
 * `hesapSecimi.ts`; başlığı istek katmanı ekliyor). Davet bağlantısı tek
 * kullanımlık ve 7 gün geçerli; kabul için davet edilen e-postayla giriş gerekir.
 */

export const IZINLER = [
  'projeler',
  'gorevler',
  'destek',
  'dosyalar',
  'faturalar',
  'siteler',
  'raporlar',
  'krediler',
  'abonelikler',
  'mesajlar',
  'asistanlar',
  'qr',
  'kartvizit',
  'menu',
  // Faz 4A — API anahtarları ve webhook'lar.
  'api',
  'randevu',
  // Faz 4W — otomasyon kuralları.
  'otomasyon',
  // Faz 5A — AI asistan ve bilgi bankası.
  'asistan',
] as const;
export type Izin = (typeof IZINLER)[number];
export type UyeRolu = 'yonetici' | 'uye' | 'fatura';
export type Rol = UyeRolu | 'sahip';
export type UyeDurumu = 'davet' | 'aktif' | 'pasif' | 'suresi_doldu';

export interface Hesap {
  hesap_email: string;
  ad?: string | null;
  rol: Rol;
  izinler: Izin[];
  kendi: boolean;
}

export interface HesapUyesi {
  id: number;
  hesap_email: string;
  uye_email: string;
  rol: UyeRolu;
  izinler: Izin[];
  durum: UyeDurumu;
  davet_bitis?: string | null;
  ekleyen?: string | null;
  olusturma?: string | null;
  son_kullanim?: string | null;
}

export interface UyeListesi {
  hesap_email: string;
  hesap_adi?: string | null;
  rolum: Rol;
  izinlerim: Izin[];
  yonetebilir: boolean;
  ben: string;
  izinler: Izin[];
  roller: Record<UyeRolu, Izin[]>;
  uyeler: HesapUyesi[];
}

export interface DavetYaniti {
  uye: HesapUyesi;
  baglanti: string;
  eposta_durumu: string;
  eposta_ayrinti?: string;
}

export interface DavetBilgisi {
  durum: UyeDurumu;
  hesap_adi?: string | null;
  hesap_eposta: string;
  davet_eposta: string;
  rol: UyeRolu;
  izinler: Izin[];
  davet_bitis?: string | null;
}

export class EkipHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
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

function hataCoz(durum: number, detay: unknown): EkipHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new EkipHatasi(durum, kod, ek);
  }
  return new EkipHatasi(durum, durum === 401 ? 'oturum_gerekli' : 'genel');
}

async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    throw hataCoz(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

/** Ekip yönetimi: `hesapEmail` verilirse ajans yöneticisi uçları (müşteri adına). */
function taban(hesapEmail?: string): string {
  return hesapEmail
    ? `/api/v1/musteri-hesaplari/${encodeURIComponent(hesapEmail)}/uyeler`
    : '/api/v1/hesabim/uyeler';
}

export async function hesaplarimiGetir(): Promise<{ ben: string; hesaplar: Hesap[] }> {
  const g = await istek<{ ben: string; hesaplar: Hesap[] }>('GET', '/api/v1/hesaplarim');
  return { ben: g?.ben ?? '', hesaplar: Array.isArray(g?.hesaplar) ? g.hesaplar : [] };
}

export function uyeleriGetir(hesapEmail?: string): Promise<UyeListesi> {
  return istek('GET', taban(hesapEmail));
}

export function uyeDavetEt(
  girdi: { email: string; rol: UyeRolu; izinler?: Izin[] },
  hesapEmail?: string
): Promise<DavetYaniti> {
  return istek('POST', taban(hesapEmail), girdi as unknown as Record<string, unknown>);
}

export function uyeGuncelle(
  id: number,
  girdi: { rol?: UyeRolu; izinler?: Izin[]; durum?: 'aktif' | 'pasif' },
  hesapEmail?: string
): Promise<HesapUyesi> {
  return istek('PUT', `${taban(hesapEmail)}/${id}`, girdi as unknown as Record<string, unknown>);
}

export function uyeSil(id: number, hesapEmail?: string): Promise<{ silindi: number }> {
  return istek('DELETE', `${taban(hesapEmail)}/${id}`);
}

export function davetiYenile(id: number, hesapEmail?: string): Promise<DavetYaniti> {
  return istek('POST', `${taban(hesapEmail)}/${id}/davet-yenile`);
}

/** Girişsiz: davet bilgisi (e-postalar maskeli). */
export async function davetBilgisi(jeton: string): Promise<DavetBilgisi> {
  const yanit = await fetch(`${getAPIBaseURL()}/api/v1/hesap-davet/${encodeURIComponent(jeton)}`);
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) throw hataCoz(yanit.status, (govde as { detail?: unknown } | null)?.detail);
  return govde as DavetBilgisi;
}

/** Giriş gerekli: daveti kabul eder (yalnız davet edilen e-postayla). */
export function davetKabul(jeton: string): Promise<{ hesap_email: string; hesap_adi?: string | null; rol: UyeRolu }> {
  return istek('POST', `/api/v1/hesap-davet/${encodeURIComponent(jeton)}/kabul`);
}

/** Ön yüz sekme anahtarı → hesap izni (biri yeterli). Sunucu zaten 403 veriyor; bu yalnız düzen için. */
export const SEKME_IZINLERI: Record<string, Izin[]> = {
  projects: ['projeler'],
  invoices: ['faturalar'],
  krediler: ['krediler'],
  tickets: ['destek'],
  raporlar: ['raporlar', 'abonelikler'],
  sitem: ['siteler'],
  analiz: ['siteler'],
  dosyalar: ['dosyalar'],
  mesajlar: ['mesajlar'],
  asistanlar: ['asistanlar'],
  qr: ['qr'],
  kartvizit: ['kartvizit'],
  menu: ['menu'],
  api: ['api'],
  randevu: ['randevu'],
  otomasyon: ['otomasyon'],
  aiAsistan: ['asistan'],
};
