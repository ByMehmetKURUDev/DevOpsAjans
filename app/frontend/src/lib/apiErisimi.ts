import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { client } from '@/lib/sdkClient';

/**
 * Faz 4A — API anahtarları, webhook uç noktaları, teslimat geçmişi, API belgesi.
 *
 * Yönetici `/api/v1/api-erisimi/yonetim/...`, müşteri `/api/v1/api-erisimim/...`
 * (etkin hesap `X-MK-Hesap` başlığıyla — istek katmanı ekliyor). İki panel aynı
 * bileşeni kullanıyor; yalnız taban yol değişiyor.
 *
 * Ham anahtar (`mk_live_…`) ve webhook sırrı (`whsec_…`) yalnız oluşturma/yenileme
 * yanıtında gelir; bileşen bunları yalnız o an bellekte tutar, hiçbir yere yazmaz.
 *
 * Bu dosya yalnız "API ve webhook" sekmesi açıldığında (lazy parçada) iniyor.
 */

export type ApiMod = 'yonetici' | 'musteri';

export interface KapsamBilgisi {
  anahtar: string;
  yazma: boolean;
  yalniz_ajans: boolean;
  izinli: boolean;
}

export interface OlayBilgisi {
  anahtar: string;
  varsayilan: boolean;
  yuksek_hacim: boolean;
}

export interface ApiMeta {
  sahip_tur: 'ajans' | 'musteri';
  hesap: string | null;
  kapsamlar: KapsamBilgisi[];
  olaylar: OlayBilgisi[];
  anahtar_siniri: number;
  anahtar_sayisi: number;
  webhook_siniri: number;
  webhook_sayisi: number;
  dakika_siniri: number;
  onerilen_ajans_suresi_gun: number;
  en_cok_deneme: number;
  pasif_esigi: number;
  api_taban: string;
  mcp_url: string;
  openapi_url: string;
}

export type AnahtarDurumu = 'aktif' | 'iptal' | 'suresi_doldu';

export interface ApiAnahtari {
  id: number;
  ad: string;
  onek: string;
  sahip_tur: 'ajans' | 'musteri';
  hesap_email: string | null;
  kapsamlar: string[];
  ip_izinleri: string[];
  dakika_siniri: number;
  son_kullanma: string | null;
  olusturan: string | null;
  son_kullanim_at: string | null;
  son_ip: string | null;
  iptal_at: string | null;
  durum: AnahtarDurumu;
  olusturma: string | null;
}

export interface WebhookUcu {
  id: number;
  sahip_tur: 'ajans' | 'musteri';
  hesap_email: string | null;
  url: string;
  aciklama: string | null;
  olaylar: string[];
  tum_musteriler: boolean;
  aktif: boolean;
  pasif_sebebi: string | null;
  ardisik_hata: number;
  son_basari_at: string | null;
  son_hata_at: string | null;
  gizli_gecis_bitis: string | null;
  bekleyen: number;
  olusturan: string | null;
  olusturma: string | null;
}

export type TeslimatDurumu = 'bekliyor' | 'basarili' | 'vazgecildi' | 'atlandi';

export interface Deneme {
  deneme_no: number;
  tetik: 'otomatik' | 'elle' | 'test';
  durum_kodu: number | null;
  sure_ms: number | null;
  yanit: string | null;
  hata: string | null;
  basarili: boolean;
  zaman: string | null;
}

export interface Teslimat {
  id: number;
  olay_id: string;
  tur: string;
  durum: TeslimatDurumu;
  deneme_sayisi: number;
  sonraki_deneme: string | null;
  son_durum_kodu: number | null;
  son_sure_ms: number | null;
  son_yanit: string | null;
  son_hata: string | null;
  govde: unknown;
  olusturma: string | null;
  denemeler?: Deneme[];
}

export interface DenemeSonucu {
  teslimat_id?: number;
  durum?: TeslimatDurumu;
  basarili?: boolean;
  durum_kodu?: number | null;
  sure_ms?: number;
  hata?: string | null;
  deneme_no?: number;
  atlandi?: string;
}

export interface AnahtarGirdisi {
  ad: string;
  kapsamlar: string[];
  son_kullanma?: string | null;
  ip_izinleri?: string[];
  dakika_siniri?: number;
  suresiz_onay?: boolean;
}

export interface UcGirdisi {
  url?: string;
  olaylar?: string[];
  aciklama?: string | null;
  aktif?: boolean;
  tum_musteriler?: boolean;
}

export class ApiErisimHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): ApiErisimHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new ApiErisimHatasi(durum, kod, ek);
  }
  if (durum === 429) return new ApiErisimHatasi(durum, 'cok_hizli');
  if (durum === 404) return new ApiErisimHatasi(durum, 'bulunamadi');
  return new ApiErisimHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw hataCoz(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

export function apiErisimApi(mod: ApiMod) {
  const taban = mod === 'yonetici' ? '/api/v1/api-erisimi/yonetim' : '/api/v1/api-erisimim';
  const sorgu = (hepsi?: boolean) => (hepsi ? '?hepsi=true' : '');
  return {
    meta: () => istek<ApiMeta>('GET', `${taban}/meta`),
    anahtarlar: async (hepsi?: boolean) =>
      (await istek<{ items: ApiAnahtari[] }>('GET', `${taban}/anahtarlar${sorgu(hepsi)}`))?.items ?? [],
    anahtarOlustur: (g: AnahtarGirdisi) =>
      istek<{ anahtar: ApiAnahtari; ham_anahtar: string }>('POST', `${taban}/anahtarlar`, g),
    anahtarIptal: (id: number) => istek<ApiAnahtari>('POST', `${taban}/anahtarlar/${id}/iptal`),
    uclar: async (hepsi?: boolean) =>
      (await istek<{ items: WebhookUcu[] }>('GET', `${taban}/webhooklar${sorgu(hepsi)}`))?.items ?? [],
    ucOlustur: (g: UcGirdisi) => istek<{ uc: WebhookUcu; gizli: string }>('POST', `${taban}/webhooklar`, g),
    ucGuncelle: (id: number, g: UcGirdisi) => istek<WebhookUcu>('PUT', `${taban}/webhooklar/${id}`, g),
    ucSil: (id: number) => istek<{ silindi: number }>('DELETE', `${taban}/webhooklar/${id}`),
    gizliYenile: (id: number) => istek<{ uc: WebhookUcu; gizli: string }>('POST', `${taban}/webhooklar/${id}/gizli-yenile`),
    testGonder: (id: number) => istek<DenemeSonucu & { olay_id: string }>('POST', `${taban}/webhooklar/${id}/test`),
    teslimatlar: (id: number, once?: number | null) =>
      istek<{ items: Teslimat[]; sonraki_once: number | null }>(
        'GET',
        `${taban}/webhooklar/${id}/teslimatlar?limit=20${once ? `&once=${once}` : ''}`
      ),
    yenidenGonder: (ucId: number, teslimatId: number) =>
      istek<DenemeSonucu>('POST', `${taban}/webhooklar/${ucId}/teslimatlar/${teslimatId}/yeniden-gonder`),
  };
}

export type ApiErisimApi = ReturnType<typeof apiErisimApi>;

// ---------------------------------------------------------------------------
// OpenAPI (herkese açık; kimliksiz)
// ---------------------------------------------------------------------------
export interface OpenApiParametre {
  name: string;
  in: 'query' | 'path' | 'header';
  required?: boolean;
  description?: string;
  schema?: { type?: string; enum?: string[]; default?: unknown; anyOf?: unknown[] };
}

export interface OpenApiIslem {
  summary?: string;
  description?: string;
  parameters?: OpenApiParametre[];
  requestBody?: { content?: Record<string, { schema?: { $ref?: string } }> };
  'x-kapsam'?: string | null;
}

export interface OpenApiBelgesi {
  info: { title: string; version: string; description?: string };
  paths: Record<string, Record<string, OpenApiIslem>>;
  components?: { schemas?: Record<string, { properties?: Record<string, { description?: string }>; required?: string[] }> };
}

export async function openapiGetir(): Promise<OpenApiBelgesi> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}/api/public/v1/openapi.json`);
  } catch {
    throw new ApiErisimHatasi(0, 'ag');
  }
  if (!yanit.ok) throw new ApiErisimHatasi(yanit.status, 'genel');
  return (await yanit.json()) as OpenApiBelgesi;
}

/** i18n anahtarlarında `:` ad alanı, `.` iç içe ayırıcı: kapsam/olay adları için güvenli biçim. */
export const anahtarAdi = (ad: string) => ad.replace(/[:.]/g, '_');

export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof ApiErisimHatasi) {
    return t(`apiErisimi.hata.${e.kod}`, { ...e.ek, defaultValue: t('apiErisimi.hata.genel') }) as string;
  }
  return t('apiErisimi.hata.genel');
}

/** YYYY-MM-DD (yerel) → gün sonu ISO (UTC). */
export function gunSonuIso(gun: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(gun)) return null;
  const [y, a, g] = gun.split('-').map(Number);
  return new Date(y, a - 1, g, 23, 59, 59).toISOString();
}

export function gunEkle(gun: number): string {
  const d = new Date();
  d.setDate(d.getDate() + gun);
  const iki = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${iki(d.getMonth() + 1)}-${iki(d.getDate())}`;
}
