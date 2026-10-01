import { getAPIBaseURL } from '@/lib/config';
import { client } from '@/lib/sdkClient';

/**
 * Ücretsiz Site Analiz Raporu — tipler ve uç çağrıları.
 *
 * Arka uç siteyi dışarıdan inceleyip altı bölümde puanlıyor. Bulgular metin
 * TAŞIMIYOR: `kod` + `deger` geliyor, cümleyi ön yüz yedi dilde kuruyor
 * (`siteAnalizi.bulgu.<kod>.baslik|neden|oneri`).
 *
 * Herkese açık uçlar (analiz, tam rapor isteği, jetonlu rapor) düz `fetch`
 * ile çağrılıyor: girişsiz sayfada SDK istemcisini kurmaya gerek yok ve
 * 429/410 gibi durum kodlarını doğrudan okuyabiliyoruz. Yönetici ve müşteri
 * uçları oturum jetonu istediği için SDK üzerinden.
 */

export type BolumAnahtari = 'hiz' | 'seo' | 'icerik' | 'teknik' | 'guvenlik' | 'ai';
export type Seviye = 'hata' | 'uyari' | 'bilgi' | 'iyi';

export const BOLUM_SIRASI: BolumAnahtari[] = ['hiz', 'seo', 'icerik', 'teknik', 'guvenlik', 'ai'];

export interface Bulgu {
  kod: string;
  seviye: Seviye;
  deger?: number | string | null;
}

export interface Bolum {
  anahtar: BolumAnahtari;
  puan: number | null;
  durum: 'tamam' | 'olculemedi';
  bulgular: Bulgu[];
}

export interface AnalizOzeti {
  id: number;
  alan_adi: string;
  url: string;
  puan: number | null;
  durum: string;
  bolumler: Bolum[];
  tam_rapor_icin_eposta: boolean;
  /** Faz 4G: tam rapor formunda isteğe bağlı pazarlama izni kutusu gösterilsin mi (site ayarı). */
  pazarlama_izni_sor?: boolean;
  created_at?: string | null;
}

export interface HizOlcumu {
  puan: number;
  lcp_ms?: number | null;
  cls?: number | null;
  tbt_ms?: number | null;
}

export interface RaporAyrintisi {
  son_url?: string;
  yonlendirmeler?: { url: string; durum: number }[];
  ana_sayfa_ms?: number;
  sayfalar?: { url: string; durum: number; sure_ms: number; baslik?: string }[];
  kirik_baglantilar?: { url: string; durum: number; kaynak?: string | null }[];
  denetlenen_baglanti?: number;
  hiz?: { mobil?: HizOlcumu | null; masaustu?: HizOlcumu | null };
  ssl_bitis?: string | null;
  robots_txt?: boolean;
  sitemap_adres_sayisi?: number | null;
  llms_txt?: boolean;
  notlar?: string[];
  sure_ms?: number;
}

export interface TamRapor {
  id: number;
  alan_adi: string;
  url: string;
  puan: number | null;
  durum: string;
  hata_kodu?: string | null;
  bolumler: Bolum[];
  ayrinti: RaporAyrintisi;
  created_at?: string | null;
  jeton_son?: string | null;
  jeton?: string | null;
  // Yalnız yönetici görünümünde:
  eposta?: string | null;
  ad?: string | null;
  kvkk_onay?: boolean;
  pazarlama_izni?: boolean;
  pazarlama_izni_at?: string | null;
  pazarlama_metin_surumu?: string | null;
  inquiry_id?: number | null;
  kaynak?: string | null;
  gonderildi_at?: string | null;
}

export interface AnalizSatiri {
  id: number;
  alan_adi: string;
  url: string;
  puan: number | null;
  durum: string;
  hata_kodu?: string | null;
  created_at?: string | null;
  eposta?: string | null;
  ad?: string | null;
  inquiry_id?: number | null;
  kaynak?: string | null;
}

export interface YonetimListesi {
  items: AnalizSatiri[];
  toplam: number;
  sayfa: number;
  adet: number;
}

/** Uçtan dönen hata: `kod` ön yüzde `siteAnalizi.hata.<kod>` ile çevriliyor. */
export class SiteAnaliziHatasi extends Error {
  durum: number;
  kod: string;

  constructor(durum: number, kod: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
  }
}

function kodCikar(govde: unknown): string | null {
  const detay = (govde as { detail?: unknown } | null)?.detail;
  if (detay && typeof detay === 'object' && 'kod' in (detay as Record<string, unknown>)) {
    return String((detay as { kod: unknown }).kod);
  }
  return null;
}

async function acikIstek<T>(yol: string, secenek?: { method?: string; govde?: unknown }): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}/api/v1/site-analizi${yol}`, {
      method: secenek?.method ?? 'GET',
      headers: secenek?.govde ? { 'Content-Type': 'application/json' } : undefined,
      body: secenek?.govde ? JSON.stringify(secenek.govde) : undefined,
    });
  } catch {
    throw new SiteAnaliziHatasi(0, 'ag');
  }
  let govde: unknown = null;
  try {
    govde = await yanit.json();
  } catch {
    govde = null;
  }
  if (!yanit.ok) {
    throw new SiteAnaliziHatasi(yanit.status, kodCikar(govde) ?? (yanit.status === 429 ? 'sinir_ip' : 'genel'));
  }
  return govde as T;
}

/** SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz. */
function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

/** SDK (axios) hatasını SiteAnaliziHatasi'na çevirir. */
function sdkHatasi(hata: unknown): SiteAnaliziHatasi {
  const h = hata as { status?: number; response?: { status?: number; data?: unknown } };
  const durum = h?.response?.status ?? h?.status ?? 0;
  return new SiteAnaliziHatasi(durum, kodCikar(h?.response?.data) ?? (durum === 429 ? 'sinir_musteri' : 'genel'));
}

async function oturumluIstek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    // Analiz 45 saniyeye kadar sürebiliyor; SDK'nın varsayılan zaman aşımı yetmeyebilir.
    const yanit = await client.apiCall.invoke({ method, url, data, options: { timeout: 90_000 } });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    throw sdkHatasi(hata);
  }
}

// ---------------------------------------------------------------------------
// Herkese açık
// ---------------------------------------------------------------------------
export function analizBaslat(url: string): Promise<AnalizOzeti> {
  return acikIstek<AnalizOzeti>('', { method: 'POST', govde: { url } });
}

export function tamRaporIste(
  id: number,
  // Faz 4G: onay kutusu yok (aydınlatma); pazarlama izni ayrı ve isteğe bağlı.
  girdi: { eposta: string; ad?: string; pazarlama_izni?: boolean; dil?: string },
): Promise<{ gonderildi: boolean }> {
  return acikIstek(`/${id}/tam-rapor`, { method: 'POST', govde: girdi });
}

export function raporGetir(jeton: string): Promise<TamRapor> {
  return acikIstek<TamRapor>(`/rapor/${encodeURIComponent(jeton)}`);
}

/** Faz 4G: site ayarı — tam rapor formunda pazarlama izni sorulsun mu ("1" / "0"). */
export const PAZARLAMA_AYARI = 'site_analizi_pazarlama_izni';

// ---------------------------------------------------------------------------
// Yönetici
// ---------------------------------------------------------------------------
export async function yonetimListesi(p: {
  sayfa?: number;
  adet?: number;
  eposta_var?: boolean;
}): Promise<YonetimListesi> {
  const sorgu = new URLSearchParams({
    sayfa: String(p.sayfa ?? 1),
    adet: String(p.adet ?? 20),
    eposta_var: p.eposta_var ? 'true' : 'false',
  });
  const govde = await oturumluIstek<Partial<YonetimListesi>>('GET', `/api/v1/site-analizi/yonetim?${sorgu}`);
  return {
    items: Array.isArray(govde?.items) ? govde!.items : [],
    toplam: govde?.toplam ?? 0,
    sayfa: govde?.sayfa ?? 1,
    adet: govde?.adet ?? 20,
  };
}

export function yonetimRaporu(id: number): Promise<TamRapor> {
  return oturumluIstek<TamRapor>('GET', `/api/v1/site-analizi/yonetim/${id}`);
}

// ---------------------------------------------------------------------------
// Müşteri
// ---------------------------------------------------------------------------
export function benimAnalizim(url: string): Promise<TamRapor> {
  return oturumluIstek<TamRapor>('POST', '/api/v1/site-analizi/benim', { url });
}

export async function benimListem(): Promise<AnalizSatiri[]> {
  const govde = await oturumluIstek<AnalizSatiri[]>('GET', '/api/v1/site-analizi/benim');
  return Array.isArray(govde) ? govde : [];
}

export function benimRaporum(id: number): Promise<TamRapor> {
  return oturumluIstek<TamRapor>('GET', `/api/v1/site-analizi/benim/${id}`);
}

// ---------------------------------------------------------------------------
// Görünüm yardımcıları
// ---------------------------------------------------------------------------
/** Puanın renk sınıfı: 90+ yeşil, 50+ amber, altı kırmızı. */
export function puanRengi(puan: number | null | undefined): string {
  if (puan == null) return 'text-muted-foreground';
  if (puan >= 90) return 'text-emerald-300';
  if (puan >= 50) return 'text-amber-300';
  return 'text-red-300';
}

export function puanDerecesi(puan: number | null | undefined): 'iyi' | 'orta' | 'zayif' | null {
  if (puan == null) return null;
  if (puan >= 90) return 'iyi';
  if (puan >= 50) return 'orta';
  return 'zayif';
}

/** Rapor bağlantısının tam adresi. */
export function raporAdresi(jeton: string): string {
  const koken = typeof window !== 'undefined' ? window.location.origin : 'https://mehmetkuru.dev';
  return `${koken}/rapor/${jeton}`;
}
