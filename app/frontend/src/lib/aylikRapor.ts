import { client } from '@/lib/sdkClient';
import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 2C — Aylık müşteri raporu.
 *
 * Yönetici  /api/v1/aylik-rapor (liste, olustur, önizle, not, yenile, yayinla, sil)
 * Müşteri   /api/v1/raporlarim/aylik  (modül `aylik_rapor`)
 * Açık      /api/v1/rapor-aylik/<jeton>  (yayındaki rapor; yönetici oturumuyla taslak)
 */

export interface IsKaydi {
  tarih: string | null;
  proje: string | null;
  baslik: string;
  tur: string;
}

export interface SiteSagligi {
  site_id: number;
  ad: string;
  adres: string | null;
  uptime_yuzde: number | null;
  olcum: number;
  kesinti_sayisi: number;
  kesinti_dk: number;
  kesintiler: { baslangic: string | null; bitis: string | null; sure_dk: number }[];
  alan_bitis: string | null;
  alan_kalan: number | null;
  ssl_bitis: string | null;
  ssl_kalan: number | null;
  hosting_bitis: string | null;
  hosting_kalan: number | null;
}

export interface SeoSatiri {
  site: string;
  alan_adi: string;
  puan: number | null;
  tarih: string | null;
  onceki_puan: number | null;
  degisim: number | null;
  bolumler: { anahtar: string; puan: number | null }[];
}

/** Faz 2H: ay içindeki teknik SEO/hız izleme ölçümlerinin site başına özeti. */
export interface SeoIzlemeSatiri {
  site_id: number;
  ad: string;
  olcum_sayisi: number;
  ilk_puan: number | null;
  son_puan: number | null;
  degisim: number | null;
  en_dusuk: number | null;
  en_yuksek: number | null;
  ortalama: number | null;
  son_tarih: string | null;
  son_mobil: number | null;
  son_masaustu: number | null;
  son_lcp_ms: number | null;
  son_cls: number | null;
  son_tbt_ms: number | null;
  son_kritik: string[];
  uyari_sayisi: number;
}

export interface RaporVerisi {
  donem: string;
  baslangic: string;
  bitis: string;
  olusturma: string;
  musteri_adi: string | null;
  ozet: {
    is_sayisi: number;
    isler: IsKaydi[];
    tamamlanan_projeler: { id: number; baslik: string }[];
    harcanan_kredi: number;
    yuklenen_kredi: number;
    kredi_bakiye: number | null;
    acilan_talep: number;
    cozulen_talep: number;
    sla_uyumlu: number;
    sla_ihlal: number;
    sla_uyum_yuzde: number | null;
  };
  site_sagligi: SiteSagligi[];
  seo: SeoSatiri[];
  /** Faz 2H; eski raporlarda yok. */
  seo_izleme?: SeoIzlemeSatiri[];
  plan: {
    acik_projeler: { baslik: string; asama: string | null; ilerleme: number | null; durum: string | null }[];
    acik_talepler: { no: number; konu: string; durum: string | null }[];
    bekleyen_belgeler: { baslik: string; son_tarih: string | null }[];
  };
}

export interface AylikRapor {
  id: number;
  donem: string;
  baslik: string | null;
  ozet: string | null;
  durum: 'taslak' | 'yayinlandi';
  yayin_at: string | null;
  yonetici_notu: string | null;
  veri: RaporVerisi;
  jeton?: string;
  client_email?: string;
  eposta_gonderildi_at?: string | null;
  eposta_gonderildi?: boolean;
}

export interface RaporSatiri {
  id: number;
  client_email?: string;
  donem: string;
  baslik: string | null;
  ozet: string | null;
  durum?: 'taslak' | 'yayinlandi';
  yayin_at: string | null;
  eposta_gonderildi_at?: string | null;
  jeton: string;
}

export class RaporHatasi extends Error {
  durum: number;
  kod: string;

  constructor(durum: number, kod: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
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
    throw new RaporHatasi(
      h?.response?.status ?? h?.status ?? 0,
      detay && typeof detay === 'object' && typeof detay.kod === 'string' ? detay.kod : 'genel'
    );
  }
}

export async function raporListesi(eposta?: string): Promise<RaporSatiri[]> {
  const g = await istek<RaporSatiri[]>(
    'GET',
    `/api/v1/aylik-rapor${eposta ? `?client_email=${encodeURIComponent(eposta)}` : ''}`
  );
  return Array.isArray(g) ? g : [];
}

export const raporOlustur = (eposta: string, donem: string) =>
  istek<AylikRapor>('POST', '/api/v1/aylik-rapor/olustur', { client_email: eposta, donem });
export const raporGetir = (id: number) => istek<AylikRapor>('GET', `/api/v1/aylik-rapor/${id}`);
export const raporNotu = (id: number, yonetici_notu: string) =>
  istek<AylikRapor>('PUT', `/api/v1/aylik-rapor/${id}`, { yonetici_notu });
export const raporYenile = (id: number) => istek<AylikRapor>('POST', `/api/v1/aylik-rapor/${id}/yenile`, {});
export const raporYayinla = (id: number) => istek<AylikRapor>('POST', `/api/v1/aylik-rapor/${id}/yayinla`, {});
export const raporSil = (id: number) => istek<{ silindi: number }>('DELETE', `/api/v1/aylik-rapor/${id}`);

export async function aylikRaporlarim(): Promise<RaporSatiri[]> {
  const g = await istek<RaporSatiri[]>('GET', '/api/v1/raporlarim/aylik');
  return Array.isArray(g) ? g : [];
}

/** Girişsiz rapor sayfası: oturum izi varsa jeton da gönderilir (yönetici taslağı önizler). */
export async function acikRapor(jeton: string): Promise<AylikRapor> {
  const basliklar: Record<string, string> = {};
  try {
    const j = localStorage.getItem('token');
    if (j) basliklar.Authorization = `Bearer ${j}`;
  } catch {
    /* gizli sekme */
  }
  const yanit = await fetch(`${getAPIBaseURL()}/api/v1/rapor-aylik/${encodeURIComponent(jeton)}`, { headers: basliklar });
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) {
    const kod = (govde as { detail?: { kod?: string } } | null)?.detail?.kod;
    throw new RaporHatasi(yanit.status, typeof kod === 'string' ? kod : 'genel');
  }
  return govde as AylikRapor;
}

export function donemAdi(donem: string, dil: string): string {
  const [y, a] = (donem || '').split('-').map(Number);
  if (!y || !a) return donem;
  try {
    return new Date(y, a - 1, 1).toLocaleDateString(dil, { month: 'long', year: 'numeric' });
  } catch {
    return donem;
  }
}

export function oncekiDonem(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
