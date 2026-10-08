import { client } from '@/lib/sdkClient';

/**
 * Faz 11A — yönetici "Genel bakış" özeti (`GET /api/v1/yonetim-ozeti`).
 *
 * Kalemlerin tanımı arka uçta (`services/yonetim_ozeti.py`). Hesaplanamayan kalem `null`
 * gelir; ekran "veri yok" der (örnek/uydurma değer yok). Sunucu önbelleği yok; burada
 * yalnız kısa bir bellek var: sekmeye geri dönülünce son özet hemen çizilsin, arkada yenilensin.
 */

export interface ParaToplami {
  para_birimi: string;
  tutar: number;
}

export interface AcilTalep {
  talep_id: number;
  kod: string;
  baslik: string;
  musteri: string | null;
  musteri_eposta: string | null;
  oncelik: 'acil' | 'yuksek' | 'normal' | 'dusuk';
  hizmet: string | null;
  hedef_turu: 'ilk_yanit' | 'cozum';
  hedef: string;
  baslangic: string;
  kalan_sn: number;
  toplam_sn: number;
  durum: 'asildi' | 'yaklasiyor' | 'zamaninda';
  siradaki: number;
}

export interface Tahsilat {
  tutar: number;
  para_birimi: string;
  onceki: number;
  degisim_yuzde: number | null;
  seri: number[];
  gunler: string[];
}

export interface IsSayaci {
  toplam: number;
  gorev: number;
  destek: number;
  is_emri: number;
  onceki: number;
  degisim_yuzde: number | null;
  seri: number[];
}

export interface SlaUyumu {
  uyum_yuzde: number;
  karar_sayisi: number;
  ilk_yanit_ort_dk: number | null;
  onceki_uyum_yuzde: number | null;
  degisim_puan: number | null;
}

export interface HatDugumu {
  sayi: number;
  bolum: string;
}

export interface HizmetHatti {
  yeni_talep: HatDugumu;
  teklif: HatDugumu & { toplamlar: ParaToplami[] };
  sozlesme: HatDugumu;
  proje: HatDugumu & { ort_ilerleme: number | null };
  teslim: HatDugumu;
  fatura: HatDugumu & { kalanlar: ParaToplami[] };
  donusum: { talep_teklif: number | null; teklif_kabul: number | null; tahsilat_gun: number | null };
}

export interface Aktivite {
  bugun: (number | null)[];
  dun: number[];
  toplam_bugun: number;
  toplam_dun: number;
  kaynak: string;
}

export interface Kategori {
  dagilim: { ad: string; sayi: number }[];
  toplam: number;
  bu_ay_yeni: number;
  ort_sure_gun: number | null;
  en_hizli: { ad: string; artis_yuzde: number } | null;
}

export interface SahaIsi {
  id: number;
  no: string;
  baslik: string;
  tur: string;
  durum: string;
  oncelik: string;
  ilerleme: number;
  plan_bas: string | null;
  musteri: string | null;
  firma: string | null;
  teknisyenler: string[];
}

export interface SahaTeknisyeni {
  id: number;
  ad: string;
  renk: string | null;
  durum: string;
  is_no: string;
  is_baslik: string;
  ilerleme: number;
}

export interface Saha {
  isler: SahaIsi[];
  is_sayisi: number;
  teknisyenler: SahaTeknisyeni[];
  aktif: number;
  bolum: string;
}

export type SonIsTuru = 'proje' | 'destek' | 'is_emri' | 'teklif';

export interface SonIs {
  tur: SonIsTuru;
  id: number;
  kod: string;
  musteri: string | null;
  hizmet: string | null;
  kategori: string | null;
  durum: string | null;
  oncelik: string | null;
  sorumlu: string | null;
  tutar: number | null;
  para_birimi: string | null;
  zaman: string | null;
  bolum: string;
}

export interface OzetBildirimi {
  id: number;
  tur: string;
  baslik: string;
  govde: string | null;
  baglanti: string | null;
  zaman: string | null;
  okundu: boolean;
}

export interface YonetimOzeti {
  olusturma: string;
  acil: AcilTalep | null;
  kpi: {
    tahsilat: Tahsilat | null;
    acik_isler: IsSayaci | null;
    tamamlanan: IsSayaci | null;
    sla: SlaUyumu | null;
  };
  hizmetHatti: HizmetHatti | null;
  aktivite: Aktivite | null;
  kategori: Kategori | null;
  saha: Saha | null;
  sonIsler: SonIs[] | null;
  bildirimler: OzetBildirimi[] | null;
}

/** Sunucudan alınan özet + alındığı an (istemci saati; geri sayımda saat farkı için). */
export interface AlinanOzet {
  veri: YonetimOzeti;
  alindi: number;
}

/** Kısa bellek: sekmeye dönünce bu kadar yeni özet beklemeden çizilir. */
const BELLEK_SURESI = 30_000;
let bellek: AlinanOzet | null = null;

export function bellektekiOzet(): AlinanOzet | null {
  return bellek && Date.now() - bellek.alindi < BELLEK_SURESI ? bellek : null;
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

export async function ozetGetir(): Promise<AlinanOzet> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/yonetim-ozeti' });
  const veri = govdeyiAc<YonetimOzeti>(yanit);
  if (!veri || typeof veri !== 'object' || !('kpi' in veri)) throw new Error('ozet_bos');
  bellek = { veri, alindi: Date.now() };
  return bellek;
}
