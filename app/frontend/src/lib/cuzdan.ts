import { formGonder, istek } from '@/lib/belge';

/**
 * Faz 5C — Cüzdan ve bakiye (müşteri avansı) uçları.
 *
 * Müşteri ajansa avans yatırır (yönetici elle kaydeder ya da müşteri havale/EFT/nakit bildirir → yönetici onaylar);
 * faturalar bu bakiyeden tamamen ya da kısmen ödenir. Tutarlar sunucuda kuruş, burada TL (ondalık) gelir/gider.
 * Para birimi dönüşümü yok: fatura yalnız kendi para birimindeki bakiyeden ödenir.
 */

export type HareketTuru = 'yukleme' | 'harcama' | 'iade' | 'duzeltme' | 'ters_kayit';
export type TalepDurumu = 'beklemede' | 'onaylandi' | 'reddedildi' | 'iptal';
export const YUKLEME_YONTEMLERI = ['havale', 'eft', 'nakit', 'diger'] as const;
export type YuklemeYontemi = (typeof YUKLEME_YONTEMLERI)[number];
export const CUZDAN_PARA_BIRIMLERI = ['TRY', 'USD', 'EUR', 'GBP'] as const;

export interface CuzdanBakiyesi {
  id: number;
  hesap_email: string;
  ad?: string | null;
  para_birimi: string;
  bakiye: number;
  dusuk_esik: number | null;
  dusuk_uyari: boolean;
  son_hareket_at: string | null;
}

export interface CuzdanHareketi {
  id: number;
  tur: HareketTuru;
  tutar: number;
  sonra: number;
  para_birimi: string;
  tarih: string | null;
  yontem: string | null;
  fatura_id: number | null;
  fatura_no: string | null;
  talep_id: number | null;
  bagli_id: number | null;
  notu: string | null;
  gerekce: string | null;
  yazan_rol: string;
  dekont_var: boolean;
  created_at: string | null;
  ters_edildi: boolean;
  ters_id: number | null;
  /** Yalnız yönetici */
  yazan?: string | null;
  hesap_email?: string;
  odeme_id?: number | null;
  ters_edilebilir?: boolean;
}

export interface YuklemeTalebi {
  id: number;
  para_birimi: string;
  tutar: number;
  yontem: string;
  odeme_tarihi: string | null;
  referans: string | null;
  dekont_var: boolean;
  notu: string | null;
  durum: TalepDurumu;
  ret_nedeni: string | null;
  karar_at: string | null;
  created_at: string | null;
  hareket_id: number | null;
  hesap_email?: string;
  kisi_email?: string | null;
  karar_veren?: string | null;
  ad?: string | null;
}

export interface CuzdanAyarlari {
  referans: string | null;
  otomatik_odeme: boolean;
  otomatik_kismi: boolean;
  otomatik_zaman: 'kesilince' | 'vadesinde';
  otomatik_baslangic: string | null;
  onay_metni_surumu: string | null;
  guncel_onay_metni_surumu: string;
}

export interface BankaBilgisi {
  banka_adi: string;
  hesap_sahibi: string;
  iban: string;
  aciklama: string;
  var: boolean;
}

export interface MusteriCuzdani {
  bakiyeler: CuzdanBakiyesi[];
  ayarlar: CuzdanAyarlari;
  banka: BankaBilgisi;
  talepler: YuklemeTalebi[];
  son_hareketler: CuzdanHareketi[];
  para_birimleri: string[];
  yontemler: string[];
}

export interface HareketSayfasi {
  items: CuzdanHareketi[];
  toplam: number;
  sayfa: number;
  adet: number;
}

export interface FaturaBakiyeBilgisi {
  fatura_id: number;
  invoice_no: string;
  para_birimi: string;
  bakiye: number;
  kalan: number;
  uygulanabilir: boolean;
  neden: string | null;
  onerilen: number;
}

export interface OdemeSonucu {
  tekrar: boolean;
  hareket: CuzdanHareketi;
  bakiye: number;
  para_birimi: string;
  fatura: { id: number; status?: string | null; bakiye?: { kalan: number } | null };
}

/** Aynı "öde" isteği iki kez gelirse (çift tıklama, ağ tekrarı) sunucu tek harcama yapar. */
export function istekAnahtari(): string {
  try {
    return crypto.randomUUID().replace(/-/g, '');
  } catch {
    return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
  }
}

// ---------------------------------------------------------------------------
// Müşteri
// ---------------------------------------------------------------------------
const M = '/api/v1/cuzdanim';

export const cuzdanim = () => istek<MusteriCuzdani>('GET', M);
export const hareketlerim = (paraBirimi?: string, sayfa = 1) =>
  istek<HareketSayfasi>('GET', `${M}/hareketler?sayfa=${sayfa}${paraBirimi ? `&para_birimi=${encodeURIComponent(paraBirimi)}` : ''}`);
export const ekstrem = (paraBirimi: string, bicim: 'pdf' | 'csv', dil: string) =>
  `${M}/ekstre?para_birimi=${encodeURIComponent(paraBirimi)}&bicim=${bicim}&dil=${encodeURIComponent(dil)}`;

export function yuklemeTalebiGonder(veri: {
  tutar: string;
  para_birimi: string;
  yontem: string;
  odeme_tarihi?: string;
  notu?: string;
  dekont?: File | null;
}): Promise<{ talep: YuklemeTalebi }> {
  const f = new FormData();
  f.append('tutar', veri.tutar);
  f.append('para_birimi', veri.para_birimi);
  f.append('yontem', veri.yontem);
  if (veri.odeme_tarihi) f.append('odeme_tarihi', veri.odeme_tarihi);
  if (veri.notu) f.append('notu', veri.notu);
  if (veri.dekont) f.append('dekont', veri.dekont);
  return formGonder(`${M}/yukleme-talepleri`, f);
}

export const talebiIptalEt = (id: number) => istek<{ talep: YuklemeTalebi }>('POST', `${M}/yukleme-talepleri/${id}/iptal`, {});
export const ayarlarimiYaz = (veri: Partial<{
  otomatik_odeme: boolean;
  onay: boolean;
  otomatik_kismi: boolean;
  otomatik_zaman: string;
  dusuk_esikler: Record<string, string | null>;
}>) => istek<CuzdanAyarlari>('PUT', `${M}/ayarlar`, veri);
export const faturamiBakiyedenOde = (faturaId: number, tutar: string | null, anahtar: string) =>
  istek<OdemeSonucu>('POST', `${M}/faturalar/${faturaId}/ode`, { tutar: tutar || null, istek_anahtari: anahtar });
export const odemeSayfasiBakiyesi = (jeton: string) =>
  istek<FaturaBakiyeBilgisi>('GET', `${M}/odeme/${encodeURIComponent(jeton)}`);

// ---------------------------------------------------------------------------
// Yönetici
// ---------------------------------------------------------------------------
const Y = '/api/v1/cuzdan-yonetim';

export interface YoneticiListesi {
  hesaplar: CuzdanBakiyesi[];
  toplamlar: { para_birimi: string; bakiye: number }[];
  bekleyen_talepler: YuklemeTalebi[];
  para_birimleri: string[];
  yontemler: string[];
  banka: BankaBilgisi;
}

export interface HesapAyrintisi {
  hesap_email: string;
  ad: string | null;
  bakiyeler: CuzdanBakiyesi[];
  ayarlar: CuzdanAyarlari;
  hareketler: HareketSayfasi;
  talepler: YuklemeTalebi[];
}

export const yoneticiListesi = (q = '') => istek<YoneticiListesi>('GET', `${Y}/hesaplar${q ? `?q=${encodeURIComponent(q)}` : ''}`);
export const hesapAyrintisi = (eposta: string, paraBirimi?: string, sayfa = 1) =>
  istek<HesapAyrintisi>(
    'GET',
    `${Y}/hesap?eposta=${encodeURIComponent(eposta)}&sayfa=${sayfa}${paraBirimi ? `&para_birimi=${encodeURIComponent(paraBirimi)}` : ''}`
  );
export const yoneticiEkstresi = (eposta: string, paraBirimi: string, bicim: 'pdf' | 'csv', dil: string) =>
  `${Y}/ekstre?eposta=${encodeURIComponent(eposta)}&para_birimi=${encodeURIComponent(paraBirimi)}&bicim=${bicim}&dil=${encodeURIComponent(dil)}`;

export function elleYukle(veri: {
  hesap_email: string;
  tutar: string;
  para_birimi: string;
  yontem: string;
  tarih?: string;
  notu?: string;
  dekont?: File | null;
}): Promise<{ hareket: CuzdanHareketi; bakiye: number }> {
  const f = new FormData();
  f.append('hesap_email', veri.hesap_email);
  f.append('tutar', veri.tutar);
  f.append('para_birimi', veri.para_birimi);
  f.append('yontem', veri.yontem);
  if (veri.tarih) f.append('tarih', veri.tarih);
  if (veri.notu) f.append('notu', veri.notu);
  if (veri.dekont) f.append('dekont', veri.dekont);
  return formGonder(`${Y}/yukle`, f);
}

export const bakiyeIadeEt = (veri: { hesap_email: string; para_birimi: string; tutar: string; yontem: string; tarih?: string; notu?: string }) =>
  istek<{ hareket: CuzdanHareketi; bakiye: number }>('POST', `${Y}/iade`, veri);
export const bakiyeDuzelt = (veri: { hesap_email: string; para_birimi: string; tutar: string; gerekce: string }) =>
  istek<{ hareket: CuzdanHareketi; bakiye: number }>('POST', `${Y}/duzeltme`, veri);
export const tersKayit = (hareketId: number, gerekce: string) =>
  istek<{ hareket: CuzdanHareketi; bakiye: number }>('POST', `${Y}/hareketler/${hareketId}/ters`, { gerekce });
export const hareketDekontu = (hareketId: number) => istek<{ adres: string }>('GET', `${Y}/hareketler/${hareketId}/dekont`);
export const talepDekontu = (talepId: number) => istek<{ adres: string }>('GET', `${Y}/talepler/${talepId}/dekont`);
export const talebiOnayla = (talepId: number, veri: { tutar?: string; notu?: string } = {}) =>
  istek<{ talep: YuklemeTalebi; bakiye: number }>('POST', `${Y}/talepler/${talepId}/onayla`, veri);
export const talebiReddet = (talepId: number, neden: string) =>
  istek<{ talep: YuklemeTalebi }>('POST', `${Y}/talepler/${talepId}/reddet`, { neden });
export const faturaBakiyesi = (faturaId: number) => istek<FaturaBakiyeBilgisi>('GET', `${Y}/faturalar/${faturaId}`);
export const faturayaUygula = (faturaId: number, tutar: string | null, anahtar: string) =>
  istek<OdemeSonucu>('POST', `${Y}/faturalar/${faturaId}/uygula`, { tutar: tutar || null, istek_anahtari: anahtar });
export const bankaAyarlari = () =>
  istek<{ kayitli: Omit<BankaBilgisi, 'var'>; gosterilen: BankaBilgisi }>('GET', `${Y}/ayarlar`);
export const bankaAyarlariniYaz = (veri: Partial<Omit<BankaBilgisi, 'var'>>) =>
  istek<{ kayitli: Omit<BankaBilgisi, 'var'>; gosterilen: BankaBilgisi }>('PUT', `${Y}/ayarlar`, veri);
