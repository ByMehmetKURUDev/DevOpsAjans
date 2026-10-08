import { client } from '@/lib/sdkClient';

/**
 * Faz 11B — müşteri paneli "Genel bakış" özeti (`GET /api/v1/musteri-ozeti`).
 *
 * Tek istek; etkin hesap `X-MK-Hesap` başlığıyla (sdkClient ekliyor). İzni/modülü olmayan ya da
 * hesaplanamayan kalem `null` gelir — ön yüz o kartı hiç çizmez. Kısa bellek (30 sn, hesap başına):
 * sekmeye dönünce özet beklemeden çizilir, arkada tazelenir. Karar/ödeme sonrası `ozetiUnut()`.
 */

export interface GorevOzeti {
  id: number;
  baslik: string;
  tarih: string | null;
  kilometre_tasi: boolean;
}

export interface Karsilama {
  hitap: string | null;
  hesap_adi: string | null;
  proje: { id: number; baslik: string; yuzde: number | null; kategori: string | null } | null;
  siradaki: GorevOzeti | null;
  onay_sayisi: number | null;
}

export interface IlerlemeHalkasiVerisi {
  id: number;
  ad: string;
  yuzde: number | null;
  tamam: number | null;
  toplam: number | null;
  tarih?: string | null;
}

export interface ProjeIlerleme {
  tur: 'grup' | 'kilometre' | 'proje';
  proje: { id: number; baslik: string } | null;
  halkalar: IlerlemeHalkasiVerisi[];
  kalem_sayisi: number;
  son_teslim: GorevOzeti | null;
  siradaki: GorevOzeti | null;
}

export interface KalanIs {
  proje_id: number;
  gunler: string[];
  gercek: number[];
  plan: (number | null)[] | null;
  kalan: number;
  toplam: number;
  plan_baslangic: string | null;
  plan_bitis: string | null;
  plan_farki_gun: number | null;
}

export interface EkipKisisi {
  ad: string;
  bas_harf: string;
  hizmet: string | null;
  rol: 'yonetici' | 'calisan';
}

export interface Ekip {
  kisiler: EkipKisisi[];
  ort_yanit_dk: number | null;
}

export type OnayTuru = 'teslimat' | 'teklif_kabul' | 'icerik' | 'teklif' | 'sozlesme' | 'belge';
export type OnayEylemi = 'onay' | 'revizyon' | 'kabul' | 'red' | 'okundu' | 'incele';

export interface OnayOgesi {
  tur: OnayTuru;
  id: number;
  baslik: string;
  tarih: string | null;
  eylemler: OnayEylemi[];
  son_kullanma?: string | null;
  // teslimat
  asama?: string | null;
  not?: string | null;
  // teklif / teklif_kabul
  kod?: string | null;
  tutar?: number | null;
  para_birimi?: string | null;
  gecerlilik?: string | null;
  // içerik
  gorsel?: number;
  kelime?: number | null;
  kanallar?: string[];
  // belge
  belge_turu?: string;
  surum?: number;
}

export interface OnayBekleyen {
  toplam: number;
  ogeler: OnayOgesi[];
  revizyon: { hak: number; kalan: number | null; kullanilan: number; asildi: boolean } | null;
}

export interface Toplanti {
  id: number;
  baslik: string;
  baslangic: string | null;
  bitis: string | null;
  sure_dk: number | null;
  yer_turu: 'cevrimici' | 'yuz_yuze' | 'telefon' | string;
  durum: string;
  katilimcilar: { bas_harf: string; tur: 'ekip' | 'dis'; ben: boolean }[];
  katilimci_sayisi: number;
  katilimci_miyim: boolean;
  yanitim: 'bekliyor' | 'katilacak' | 'katilamayacak' | 'belki' | null;
  katil_baglantisi: string | null;
  katil_yakinda: boolean;
}

export interface Hedef {
  kaynak: 'ajans' | 'kendi';
  id: number;
  baslik: string;
  donem: { ad: string; tur: string; yil: number | null; ceyrek: number | null; baslangic: string; bitis: string };
  beklenen: number;
  ilerleme: number | null;
  durum: 'tamam' | 'yolunda' | 'riskli' | 'geride' | null;
  krler: { id: number; baslik: string; ilerleme: number }[];
  kr_sayisi: number;
  toplam: number;
}

export interface Bakiye {
  bakiyeler: { para_birimi: string; bakiye: number }[];
  otomatik_odeme: boolean;
  bekleyen_yukleme: number;
}

export interface AcikFatura {
  id: number;
  kod: string;
  kalan: number;
  toplam: number;
  para_birimi: string;
  vade: string | null;
  durum: string;
  gecikmis: boolean;
  bakiyeden: boolean;
  odeme_adresi: string | null;
}

export interface DestekTalebi {
  id: number;
  kod: string;
  baslik: string;
  durum: string;
  yanit_bekliyor: boolean;
  tarih: string | null;
}

export interface MusteriOzeti {
  olusturma: string;
  hesap: { kendi: boolean; rol: string };
  karsilama: Karsilama | null;
  projeIlerleme: ProjeIlerleme | null;
  kalanIs: KalanIs | null;
  ekip: Ekip | null;
  onayBekleyen: OnayBekleyen | null;
  toplanti: Toplanti | null;
  hedef: Hedef | null;
  bakiye: Bakiye | null;
  faturalar: { acik_sayisi: number; ogeler: AcikFatura[] } | null;
  destek: { acik_sayisi: number; ogeler: DestekTalebi[] } | null;
}

/** Kısa bellek: sekmeye dönünce bu kadar yeni özet beklemeden çizilir. */
const BELLEK_SURESI = 30_000;
let bellek: { hesap: string; veri: MusteriOzeti; alindi: number } | null = null;

export function bellektekiOzet(hesap: string): MusteriOzeti | null {
  return bellek && bellek.hesap === hesap && Date.now() - bellek.alindi < BELLEK_SURESI ? bellek.veri : null;
}

/** Karar / ödeme sonrası: bir sonraki açılış belleği kullanmasın. */
export function ozetiUnut(): void {
  bellek = null;
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

export async function musteriOzetiGetir(hesap: string): Promise<MusteriOzeti> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/musteri-ozeti' });
  const veri = govdeyiAc<MusteriOzeti>(yanit);
  if (!veri || typeof veri !== 'object' || !('karsilama' in veri)) throw new Error('ozet_bos');
  bellek = { hesap, veri, alindi: Date.now() };
  return veri;
}
