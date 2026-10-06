import { getAPIBaseURL } from '../lib/config';

/**
 * Fiyatlandırma v5 — backend'deki `routers/fiyatlandirma.py` (herkese açık,
 * `entity_guard`'a bağlı değil) ve `routers/pricing_entities.py` (katalog
 * tabloları artık `HERKESE_ACIK_OKUMA`'da, girişsiz okunabiliyor) ile
 * konuşan ince istemci.
 *
 * `@metagptx/web-sdk` üretilmiş istemcisi kullanılmıyor: `/fiyat-hesapla`
 * ve `/fiyat-teklif` entity CRUD şeklinde değil, SDK'nın bunları tanıması
 * garanti değil. `src/api/settings.ts` ile aynı düz `fetch` deseni izleniyor.
 */

const apiBase = () => `${getAPIBaseURL()}/api/v1`;

/** Dil bazlı metinler: {"en": {"ad": ...}}; boş dilde Türkçe alan kullanılır. */
export type Ceviriler = Record<string, Record<string, unknown>> | null;

export type FiyatPeriyodu = 'aylik' | 'yillik' | 'tek_seferlik' | 'kullandikca_ode';

export interface PricingProfile {
  id: number;
  kod: string;
  ad: string;
  carpan: number;
  etiket: string | null;
  sira: number;
  ceviriler?: Ceviriler;
}

export interface PricingScale {
  id: number;
  kod: string;
  sira: number;
  ad: string;
  alt_baslik: string;
  calisan_araligi: string;
  aciklama: string;
  baz_aylik_fiyat_usd: number;
  ozellikler: string[] | null;
  eklenti_limiti: string | null;
  revizyon_saat: string | null;
  populer: boolean;
  karsilastirma: Record<string, string> | null;
  ceviriler?: Ceviriler;
}

export interface PricingService {
  id: number;
  kategori: string;
  ad: string;
  baz_fiyat_usd: number;
  tek_seferlik: boolean;
  not_metni: string | null;
  yeni: boolean;
  ceviriler?: Ceviriler;
}

export interface PricingAddon {
  id: number;
  scale_kod: string;
  ad: string;
  baz_fiyat_usd: number;
  birim: string | null;
  sira: number;
  ceviriler?: Ceviriler;
}

export interface AiPmTier {
  id: number;
  kod: string;
  ad: string;
  fiyat_aylik_usd: number;
  rozet: string | null;
  ozellikler: string[] | null;
  sira: number;
  ceviriler?: Ceviriler;
}

export interface FiyatHesaplaSonucu {
  paket_fiyat: number;
  eklentiler_toplami: number;
  toplam: number;
  para_birimi: string;
  formul_notu: string | null;
  eklenti_detay: { kod: string; fiyat: number }[];
  /** Karta eklenen AI vs PM paketinin periyoda göre tutarı. */
  ai_pm_toplami?: number;
  /** Yalnız "kullandikca_ode": paketin aylık karşılığı kaç kredi. */
  kredi?: number | null;
}

export interface FiyatTeklifIstegi {
  scale?: string;
  profile?: string;
  period?: FiyatPeriyodu;
  addon_ids?: string[];
  ai_pm_tier_kod?: string;
  /** Kullandıkça Öde kredi paketi (10/25/50/100). */
  kredi_paketi?: number;
  musteri_eposta: string;
  musteri_adi?: string;
}

export interface FiyatSatinAlSonucu {
  /** Ödeme sayfası: `/ode/<jeton>`. */
  adres: string;
  invoice_id: number;
  toplam: number;
}

export interface FiyatTeklifSonucu {
  inquiry_id: number;
  invoice_id: number;
  toplam: number;
}

/** Sunucudan HTTP hatası geldiğinde kullanıcıya gösterilecek Türkçe mesajı çıkarır. */
async function ayikla(response: Response): Promise<never> {
  let detail: string | undefined;
  try {
    const body = await response.json();
    // Faz 7H: 429 gibi uçlar `{kod}` nesnesi döndürüyor; mesaj yalnız metin detayından.
    detail = typeof body?.detail === 'string' ? body.detail : undefined;
  } catch {
    /* JSON degil */
  }
  const hata = new Error(detail || `İstek başarısız (${response.status})`) as Error & { status?: number };
  hata.status = response.status;
  throw hata;
}

async function getJSON<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${apiBase()}${path}`, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  }
  const response = await fetch(url.toString());
  if (!response.ok) return ayikla(response);
  return response.json();
}

/** Public entity okuma: `/api/v1/entities/<table>/all` — artık girişsiz açık. */
async function entityAll<T>(table: string): Promise<T[]> {
  const data = await getJSON<{ items: T[] }>(`/entities/${table}/all`);
  return data.items ?? [];
}

export const fiyatlandirmaApi = {
  scales: () => entityAll<PricingScale>('pricing_scales'),
  profiles: () => entityAll<PricingProfile>('pricing_profiles'),
  services: () => entityAll<PricingService>('pricing_services'),
  addons: () => entityAll<PricingAddon>('pricing_addons'),
  aiPmTiers: () => entityAll<AiPmTier>('ai_pm_tiers'),

  hesapla: (args: { scale: string; profile: string; period: FiyatPeriyodu; addons: string[]; aiPm?: string }) =>
    getJSON<FiyatHesaplaSonucu>('/fiyat-hesapla', {
      scale: args.scale,
      profile: args.profile,
      period: args.period,
      addons: args.addons.join(','),
      ...(args.aiPm ? { ai_pm: args.aiPm } : {}),
    }),

  teklifGonder: async (istek: FiyatTeklifIstegi): Promise<FiyatTeklifSonucu> => {
    const response = await fetch(`${apiBase()}/fiyat-teklif`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(istek),
    });
    if (!response.ok) return ayikla(response);
    return response.json();
  },
  /** Satın Al: fatura + ödeme bağlantısı; dönen adrese yönlendirilir. */
  satinAl: async (istek: FiyatTeklifIstegi): Promise<FiyatSatinAlSonucu> => {
    const response = await fetch(`${apiBase()}/fiyat-satin-al`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(istek),
    });
    if (!response.ok) return ayikla(response);
    return response.json();
  },
};
