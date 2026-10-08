import { getAPIBaseURL } from '@/lib/config';
import { istek, kalemGirdisi, type BelgeOzeti, type Kalem } from '@/lib/belge';

/**
 * Faz 5K — indirim kodları.
 *
 * * Herkese açık `POST /api/v1/indirim-kodu/dogrula`: formdaki "indirim / referans kodu" alanının anlık
 *   denetimi (IP başına 10 dakikada 10 deneme; 429 = çok hızlı).
 * * Yönetici `/api/v1/indirim-kodu-yonetim`: CRUD + belge önizlemesi.
 */

export type KodTuru = 'yuzde' | 'sabit';
export type Kapsam = 'teklif' | 'fatura' | 'paket';
export const KAPSAMLAR: Kapsam[] = ['teklif', 'fatura', 'paket'];

export interface IndirimKodu {
  id: number;
  kod: string;
  aciklama: string | null;
  tur: KodTuru;
  deger: number;
  para_birimi: string | null;
  baslangic: string | null;
  bitis: string | null;
  toplam_sinir: number | null;
  kisi_basi_sinir: number | null;
  en_az_tutar: number | null;
  kapsam: Kapsam[];
  /** Geçerli paketler (fiyatlandırma ölçeği, KREDI, AI_PM); boş = hepsi. */
  paketler: string[];
  ortak_id: number | null;
  ortak_ad: string | null;
  aktif: boolean;
  kullanim: number;
  durum: 'gecerli' | 'pasif' | 'kod_baslamadi' | 'kod_suresi_doldu';
}

export interface DogrulamaSonucu {
  gecerli: boolean;
  tur?: 'indirim' | 'referans';
  kod?: string;
  indirim?: { kod: string; tur: KodTuru; deger: number; para_birimi: string | null; bitis: string | null; en_az_tutar: number | null };
  /** 429 (çok hızlı) */
  sinir?: boolean;
}

/** Ölçek dışındaki paket kimlikleri (Kullandıkça Öde kredi paketi, AI / PM). */
export const OZEL_PAKETLER = ['KREDI', 'AI_PM'] as const;

/** "Teklif al" seçiminin paket kimliği (sunucudaki `talep_paketi` ile aynı kural). */
export function secimPaketi(secim: { scale?: string; ai_pm_tier_kod?: string; kredi_paketi?: number }): string {
  if (secim.scale) return secim.scale.toUpperCase();
  if (secim.ai_pm_tier_kod) return 'AI_PM';
  return 'KREDI';
}

/** `paket`: "Teklif al" penceresinin seçili paketi — pakete uymayan kod geçersiz görünür. */
export async function koduDogrula(kod: string, paket?: string): Promise<DogrulamaSonucu> {
  try {
    const y = await fetch(`${getAPIBaseURL()}/api/v1/indirim-kodu/dogrula`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(paket ? { kod, paket } : { kod }),
    });
    const govde = (await y.json().catch(() => null)) as DogrulamaSonucu | null;
    if (y.status === 429) return { gecerli: false, sinir: true };
    return govde && typeof govde.gecerli === 'boolean' ? govde : { gecerli: false };
  } catch {
    return { gecerli: false };
  }
}

const YON = '/api/v1/indirim-kodu-yonetim';

export async function kodListesi(): Promise<IndirimKodu[]> {
  const g = await istek<IndirimKodu[]>('GET', YON);
  return Array.isArray(g) ? g : [];
}
export const kodOlustur = (g: Record<string, unknown>) => istek<IndirimKodu>('POST', YON, g);
export const kodGuncelle = (id: number, g: Record<string, unknown>) => istek<IndirimKodu>('PUT', `${YON}/${id}`, g);
export const kodSil = (id: number) => istek<{ silindi: number }>('DELETE', `${YON}/${id}`);

export interface Onizleme extends BelgeOzeti {
  kod: string | null;
  indirim: number;
  kalemler: Kalem[];
}

export const onizle = (g: { kod: string; kalemler: Kalem[]; para_birimi: string; belge_turu: 'teklif' | 'fatura'; eposta?: string; belge_id?: number }) =>
  istek<Onizleme>('POST', `${YON}/onizle`, { ...g, kalemler: g.kalemler.map(kalemGirdisi) });

/** Sunucunun eklediği "İndirim (KOD)" satırı mı? (düzenleyicide gösterilmez; kayıtta yeniden kurulur) */
export const indirimSatiriMi = (k: Kalem) => !!(k as Kalem & { indirim_kodu?: string }).indirim_kodu;
