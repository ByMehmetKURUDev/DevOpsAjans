import { client } from '@/lib/sdkClient';

/**
 * Faz 3K — Kaynaklar yönetimi (yönetici paneli).
 *
 * Uçlar `/api/v1/kaynaklar/yonetim`: liste (taslaklar dahil), ekle, tam
 * güncelle, hızlı anahtar (yayında / öne çıkan / sıra), sıralama, sil (çöp
 * kutusuna). Metinler Türkçe ana alanlarda, diğer diller `ceviriler`de.
 */

export const KAYNAK_CEVIRI_DILLERI = ['en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
export const BAGLANTI_TURLERI = ['github', 'site', 'belge', 'video'] as const;

export interface KaynakCevirisi {
  baslik?: string;
  ozet?: string;
  aciklama?: string;
  adimlar?: string[];
}

export interface YonetimKaynagi {
  id: number;
  slug: string;
  kategori: string;
  baslik: string;
  ozet: string;
  aciklama: string;
  adimlar: string[];
  ceviriler: Record<string, KaynakCevirisi>;
  etiketler: string[];
  baglanti: string;
  baglanti_turu: string;
  lisans: string | null;
  ucretsiz: boolean;
  acik_kaynak: boolean;
  youtube_short: string | null;
  one_cikan: boolean;
  sira: number;
  yayinda: boolean;
  dogrulama_tarihi: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type KaynakGirdisi = Omit<YonetimKaynagi, 'id' | 'created_at' | 'updated_at'>;

export interface YonetimKategorisi {
  anahtar: string;
  ad: Record<string, string>;
}

export interface YonetimListesi {
  kaynaklar: YonetimKaynagi[];
  kategoriler: YonetimKategorisi[];
}

export class KaynakIstekHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan?: string,
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

async function istek<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    const detay = h?.response?.data?.detail as { kod?: unknown; alan?: unknown } | undefined;
    const kod = detay && typeof detay === 'object' && typeof detay.kod === 'string' ? detay.kod : 'genel';
    const alan = detay && typeof detay === 'object' && typeof detay.alan === 'string' ? detay.alan : undefined;
    throw new KaynakIstekHatasi(h?.response?.status ?? h?.status ?? 0, kod, alan);
  }
}

const KOK = '/api/v1/kaynaklar/yonetim';

export async function yonetimListesi(): Promise<YonetimListesi> {
  const g = await istek<Partial<YonetimListesi>>('GET', KOK);
  return {
    kaynaklar: Array.isArray(g?.kaynaklar) ? g!.kaynaklar : [],
    kategoriler: Array.isArray(g?.kategoriler) ? g!.kategoriler : [],
  };
}

export function kaynakEkle(girdi: KaynakGirdisi): Promise<YonetimKaynagi> {
  return istek('POST', KOK, girdi);
}

export function kaynakGuncelle(id: number, girdi: KaynakGirdisi): Promise<YonetimKaynagi> {
  return istek('PUT', `${KOK}/${id}`, girdi);
}

export function kaynakYama(
  id: number,
  yama: Partial<Pick<YonetimKaynagi, 'yayinda' | 'one_cikan' | 'sira'>>,
): Promise<YonetimKaynagi> {
  return istek('PATCH', `${KOK}/${id}`, yama);
}

export function kaynaklariSirala(kimlikler: number[]): Promise<{ guncellenen: number }> {
  return istek('POST', `${KOK}/sirala`, { sira: kimlikler });
}

export function kaynakSil(id: number): Promise<{ silindi: number }> {
  return istek('DELETE', `${KOK}/${id}`);
}
