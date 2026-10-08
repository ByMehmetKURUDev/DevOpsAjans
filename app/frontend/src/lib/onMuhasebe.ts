import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 6M — Ön muhasebe: panel uçları ve küçük yardımcılar.
 *
 * Müşteri paneli `/api/v1/muhasebe/...` (etkin hesap `X-MK-Hesap`), ajans paneli `/api/v1/muhasebe-yonetim/...`:
 * `hesap` verilmezse ajansın KENDİ defteri (tam yönetim), verilirse müşteri hesabının SALT OKUNUR destek görünümü.
 * Tutarlar kuruş (tam sayı); para birimleri arasında dönüşüm yapılmaz. Bu dosya yalnız sekme açıldığında (lazy) iner.
 */

export type MuhasebeMod = 'musteri' | 'yonetici';
export type HesapTuru = 'kasa' | 'banka' | 'kredi_karti' | 'pos';
export type HareketTuru = 'gelir' | 'gider' | 'tahsilat' | 'odeme' | 'virman';
export type KategoriTuru = 'gelir' | 'gider';
export type CariTuru = 'musteri' | 'tedarikci' | 'her_ikisi';
export type Periyot = 'haftalik' | 'aylik' | 'uc_aylik' | 'yillik';
export type Kova = 'vadesi_gelmemis' | '0_30' | '31_60' | '61_90' | '90_ustu';
export type AktarimKaynagi = 'odeme' | 'pos' | 'hukuk' | 'saha';

export const KOVALAR: Kova[] = ['vadesi_gelmemis', '0_30', '31_60', '61_90', '90_ustu'];

export interface Hesap {
  id: number;
  tur: HesapTuru;
  ad: string;
  banka_adi: string;
  /** Tam IBAN hiç dönmez: yalnız kayıtlı olup olmadığı ve son 4 hanesi (maskeli). */
  iban_var: boolean;
  iban_maske: string | null;
  son4: string;
  para_birimi: string;
  acilis_bakiyesi: number;
  acilis_tarihi: string | null;
  arsiv: boolean;
  notlar: string;
  sira: number;
  bakiye: number;
  hareket_sayisi: number;
}

export interface Kategori {
  id: number;
  tur: KategoriTuru;
  ad: string;
  anahtar: string | null;
  ad_degisti: boolean;
  renk: string;
  arsiv: boolean;
  sira: number;
  kullanim: number;
}

export interface AktarimAyari {
  acik: boolean;
  baslangic: string | null;
  /** Açıksa her kayıt öneri olarak gelir (onaylanınca deftere). */
  onay: boolean;
  [alan: string]: unknown;
}

export interface Ayarlar {
  kapsam: string;
  firma_adi: string;
  para_birimi: string;
  uyari_yuzde: number;
  aktarim: Record<string, AktarimAyari>;
  son_esitleme: EsitlemeSonucu | null;
  son_esitleme_at: string | null;
}

export interface EsitlemeSonucu {
  tekrar: number;
  olusturulan: number;
  ters: number;
  oneri?: number;
  bekleyen_oneri?: number;
  gecikme?: number;
  atlanan: Record<string, number>;
  butce_asimi: number;
}

export interface Meta {
  yonetici: boolean;
  hesap: string | null;
  ajans: boolean;
  salt_okunur: boolean;
  /** `muhasebe_okur` izni: yalnız özet, bütçe ve raporlar. */
  okur: boolean;
  oneri_sayisi: number;
  kisi: string;
  bugun: string;
  hesap_siniri: number | null;
  ayarlar: Ayarlar;
  hesaplar: Hesap[];
  kategoriler: Kategori[];
  cari_sayisi: number;
  aktarim_kaynaklari: AktarimKaynagi[];
  aktarim_modulleri: Record<string, boolean>;
  sabitler: {
    hesap_turleri: HesapTuru[];
    hareket_turleri: HareketTuru[];
    para_birimleri: string[];
    kdv_oranlari: number[];
    periyotlar: Periyot[];
    cari_turleri: CariTuru[];
    kovalar: Kova[];
    tarih_bicimleri: string[];
    en_cok_csv: number;
    bagli_turler: string[];
  };
}

export interface Hareket {
  id: number;
  tur: HareketTuru;
  tarih: string;
  tutar: number;
  para_birimi: string;
  kdv_orani: number | null;
  kdv_tutari: number;
  kategori_id: number | null;
  kategori: { ad: string; anahtar: string | null; ad_degisti: boolean; renk: string | null } | null;
  hesap_id: number | null;
  hesap: string | null;
  hedef_hesap_id: number | null;
  hedef_hesap: string | null;
  hedef_tutar: number | null;
  hedef_para_birimi: string | null;
  cari_id: number | null;
  cari: string | null;
  vade_tarihi: string | null;
  aciklama: string;
  belge_no: string;
  etiketler: string[];
  kaynak: string;
  otomatik: boolean;
  ters: boolean;
  ters_edildi: boolean;
  tekrar_id: number | null;
  ek_sayisi: number;
  duzenlenebilir: boolean;
  created_at: string | null;
  ekler?: { id: number; ad: string; tur: string; boyut: number; created_at: string | null }[];
  butce_asimi?: number;
}

export interface Toplam {
  para_birimi: string;
  gelir: number;
  gider: number;
  tahsilat?: number;
  odeme?: number;
  virman?: number;
  net: number;
}

export interface Cari {
  id: number;
  tur: CariTuru;
  ad: string;
  para_birimi: string;
  arsiv: boolean;
  bakiye: number;
  bagli_tur: string | null;
  bagli_id: string | null;
  vergi_dairesi?: string;
  vergi_no?: string;
  eposta?: string;
  telefon?: string;
  adres?: string;
  notlar?: string;
  acilis_bakiyesi?: number;
  acilis_tarihi?: string | null;
}

export interface YasOzeti {
  kovalar: Record<Kova, number>;
  acik: number;
  fazla?: number;
  en_eski_gun: number | null;
}

export interface CariAyrinti extends Cari {
  yaslandirma_alacak: YasOzeti;
  yaslandirma_borc: YasOzeti;
  son_hareketler: Hareket[];
  bagli?: { tur: string; id: string; ad: string | null; ayrinti: string | null };
}

export interface EkstreSatiri {
  id: number | null;
  tarih: string;
  tur: string;
  aciklama: string | null;
  belge_no: string | null;
  vade: string | null;
  borc: number;
  alacak: number;
  bakiye: number;
  ters: boolean;
}

export interface Ekstre {
  cari: Cari;
  bas: string;
  bit: string;
  devreden: number;
  satirlar: EkstreSatiri[];
  toplam_borc: number;
  toplam_alacak: number;
  kapanis: number;
}

export interface Tekrar {
  id: number;
  tur: KategoriTuru;
  aciklama: string;
  tutar: number;
  para_birimi: string;
  kdv_orani: number | null;
  kategori_id: number | null;
  hesap_id: number | null;
  cari_id: number | null;
  periyot: Periyot;
  baslangic: string;
  bitis: string | null;
  sonraki: string | null;
  son_uretilen: string | null;
  aktif: boolean;
  etiketler: string[];
}

export interface ButceKalemi {
  kategori_id: number;
  ad: string;
  anahtar: string | null;
  ad_degisti: boolean;
  renk: string | null;
  para_birimi: string;
  butce: number | null;
  butce_id: number | null;
  butce_kaynak: 'ay' | 'her_ay' | null;
  gerceklesen: number;
  oran: number | null;
  kalan: number | null;
  durum: 'normal' | 'yaklasti' | 'asildi' | 'butcesiz';
  uyari_at: string | null;
}

export interface ButceDurumu {
  ay: string;
  uyari_yuzde: number;
  kalemler: ButceKalemi[];
  toplamlar: { para_birimi: string; butce: number; gerceklesen: number }[];
  asim_sayisi: number;
  tanimlar: { id: number; kategori_id: number; ay: string; tutar: number; para_birimi: string }[];
}

export interface Ozet {
  ay: string;
  bakiyeler: { para_birimi: string; bakiye: number }[];
  bu_ay: Toplam[];
  butce: { asim_sayisi: number; uyarilar: ButceKalemi[] };
  gecikmis_alacak: { para_birimi: string; tutar: number }[];
  gecikmis_cari: number;
  son_hareketler: Hareket[];
  oneri_sayisi: number;
}

/** Onay bekleyen (ya da yok sayılmış) otomatik yansıma. */
export interface Oneri {
  id: number;
  kaynak: string;
  kaynak_ref: string;
  durum: 'bekliyor' | 'yoksayildi';
  tur: KategoriTuru;
  tarih: string;
  tutar: number;
  para_birimi: string;
  kdv_orani: number | null;
  kdv_tutari: number;
  hesap_id: number | null;
  hesap: string | null;
  cari_id: number | null;
  cari: string | null;
  kategori: { ad: string | null; anahtar: string | null; ad_degisti: boolean; renk: string | null } | null;
  aciklama: string;
  belge_no: string;
  vade_tarihi: string | null;
}

export interface AylikRapor {
  yil: number;
  para_birimleri: { para_birimi: string; aylar: { ay: string; gelir: number; gider: number; net: number }[]; gelir: number; gider: number; net: number }[];
}

export interface KategoriRaporu {
  bas: string;
  bit: string;
  tur: KategoriTuru;
  para_birimleri: { para_birimi: string; toplam: number; kalemler: { kategori_id: number | null; ad: string | null; anahtar: string | null; ad_degisti: boolean; renk: string; tutar: number; oran: number }[] }[];
}

export interface KarZararKalemi {
  kategori_id: number | null;
  ad: string | null;
  anahtar: string | null;
  ad_degisti: boolean;
  renk: string;
  /** KDV hariç (kuruş). */
  tutar: number;
  kdv: number;
  brut: number;
}

export interface KarZarar {
  bas: string;
  bit: string;
  bilgilendirme: boolean;
  para_birimleri: {
    para_birimi: string;
    gelirler: KarZararKalemi[];
    giderler: KarZararKalemi[];
    toplam_gelir: number;
    toplam_gider: number;
    sonuc: number;
    marj: number | null;
  }[];
}

export interface NakitAy {
  ay: string;
  giris: number;
  cikis: number;
  net: number;
  bakiye: number;
  tahmin?: boolean;
}

export interface NakitAkisi {
  bugun: string;
  para_birimleri: {
    para_birimi: string;
    gecmis: NakitAy[];
    tahmin: NakitAy[];
    bu_ay_kalan: { giris: number; cikis: number };
    /** Önümüzdeki 30 / 60 / 90 gün: cari vadeleri + tekrarlayan kayıtlar. */
    beklenen: { gun: number; tahsilat: number; odeme: number; tekrar_giris: number; tekrar_cikis: number; net: number; bakiye: number }[];
    gecikmis: { tahsilat: number; odeme: number };
  }[];
}

export interface KdvRaporu {
  yil: number;
  bilgilendirme: boolean;
  para_birimleri: {
    para_birimi: string;
    aylar: { ay: string; hesaplanan: number; indirilecek: number; fark: number; matrah_satis: number; matrah_alis: number }[];
    hesaplanan: number;
    indirilecek: number;
    fark: number;
  }[];
}

export interface Yaslandirma {
  tarih: string;
  yon: 'alacak' | 'borc';
  satirlar: { cari_id: number; ad: string; para_birimi: string; kovalar: Record<Kova, number>; acik: number; en_eski_gun: number | null }[];
  toplamlar: { para_birimi: string; kovalar: Record<Kova, number>; acik: number }[];
}

export interface CsvOnizleme {
  basliklar: string[];
  ornek: string[][];
  satir_sayisi: number;
  esleme: Record<string, number | null>;
  tarih_bicimi: string;
  ondalik: string;
}

export interface IceAktarSonucu {
  dene: boolean;
  satir_sayisi: number;
  eklenen: number;
  tekrar: number;
  hata_sayisi: number;
  hatalar: { satir: number; kod: string; alan?: string }[];
  onizleme: { satir: number; tarih: string; tur: KategoriTuru; tutar: number; aciklama: string }[];
}

export interface MusteriHesabi {
  hesap_email: string;
  firma_adi: string | null;
  hesap_sayisi: number;
  hareket_sayisi: number;
}

export interface BaglantiAdayi {
  tur: string;
  id: string;
  ad: string | null;
  ayrinti: string | null;
}

// ---------------------------------------------------------------------------
// Hata ve istek
// ---------------------------------------------------------------------------
export class MuhasebeHatasi extends Error {
  durum: number;
  kod: string;
  ek: Record<string, unknown>;
  constructor(durum: number, kod: string, ek: Record<string, unknown> = {}) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
    this.ek = ek;
  }
}

function hataCoz(durum: number, detay: unknown): MuhasebeHatasi {
  if (detay && typeof detay === 'object' && 'kod' in (detay as Record<string, unknown>)) {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new MuhasebeHatasi(durum, String(kod), ek);
  }
  if (durum === 429) return new MuhasebeHatasi(durum, 'cok_hizli');
  if (durum === 404) return new MuhasebeHatasi(durum, 'bulunamadi');
  if (durum === 403) return new MuhasebeHatasi(durum, 'yetki_yok');
  return new MuhasebeHatasi(durum, durum === 0 ? 'ag' : 'genel');
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

function oturumBasliklari(): Record<string, string> {
  const b: Record<string, string> = { ...hesapBasliklari() };
  try {
    const j = localStorage.getItem('token');
    if (j) b.Authorization = `Bearer ${j}`;
  } catch {
    /* depolama yok */
  }
  return b;
}

async function hamIstek(url: string, init: RequestInit): Promise<Response> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, {
      ...init,
      headers: { ...oturumBasliklari(), ...(init.headers as Record<string, string> | undefined) },
    });
  } catch {
    throw new MuhasebeHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = (await yanit.json().catch(() => null)) as { detail?: unknown } | null;
    throw hataCoz(yanit.status, govde?.detail);
  }
  return yanit;
}

export function blobIndir(blob: Blob, ad: string): void {
  const adres = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = adres;
  a.download = ad;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(adres), 4000);
}

type Sorgu = Record<string, string | number | boolean | undefined | null>;

export interface HareketSuzgeci {
  bas?: string;
  bit?: string;
  tur?: string;
  hesap_id?: number;
  kategori_id?: number;
  cari_id?: number;
  kaynak?: string;
  etiket?: string;
  ara?: string;
  sayfa?: number;
  adet?: number;
}

export function muhasebeApi(mod: MuhasebeMod, hesap?: string) {
  const T = mod === 'yonetici' ? '/api/v1/muhasebe-yonetim' : '/api/v1/muhasebe';
  const u = (yol: string, q?: Sorgu) => {
    const p = new URLSearchParams();
    if (mod === 'yonetici' && hesap) p.set('hesap', hesap);
    for (const [k, v] of Object.entries(q || {})) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
    const s = p.toString();
    return `${T}${yol}${s ? `?${s}` : ''}`;
  };
  const indir = async (yol: string, q: Sorgu, ad: string) => {
    const y = await hamIstek(u(yol, q), { method: 'GET' });
    blobIndir(await y.blob(), ad);
  };
  return {
    mod,
    musteriHesaplari: () => istek<{ items: MusteriHesabi[] }>('GET', '/api/v1/muhasebe-yonetim/musteri-hesaplari'),
    meta: () => istek<Meta>('GET', u('/meta')),
    ozet: () => istek<Ozet>('GET', u('/ozet')),
    ayarlarKaydet: (g: Record<string, unknown>) => istek<Ayarlar>('PUT', u('/ayarlar'), g),
    esitle: () => istek<EsitlemeSonucu>('POST', u('/esitle'), {}),
    oneriler: (durum: 'bekliyor' | 'yoksayildi' = 'bekliyor') =>
      istek<{ items: Oneri[]; sayilar: Record<'bekliyor' | 'yoksayildi', number> }>('GET', u('/oneriler', { durum })),
    oneriOnayla: (id: number, g: Record<string, unknown> = {}) => istek<Hareket>('POST', u(`/oneriler/${id}/onayla`), g),
    oneriYoksay: (id: number) => istek<{ ok: boolean; bekleyen: number }>('POST', u(`/oneriler/${id}/yoksay`), {}),
    oneriGeriAl: (id: number) => istek<{ ok: boolean; bekleyen: number }>('POST', u(`/oneriler/${id}/geri-al`), {}),
    oneriToplu: (islem: 'onayla' | 'yoksay', idler: number[]) =>
      istek<{ islem: string; tamam: number; hatalar: { id: number; kod: string }[]; bekleyen: number }>('POST', u('/oneriler/toplu'), { islem, idler }),
    hesaplar: () => istek<{ items: Hesap[]; toplamlar: { para_birimi: string; bakiye: number }[] }>('GET', u('/hesaplar')),
    hesapEkle: (g: Record<string, unknown>) => istek<Hesap>('POST', u('/hesaplar'), g),
    hesapGuncelle: (id: number, g: Record<string, unknown>) => istek<Hesap>('PUT', u(`/hesaplar/${id}`), g),
    hesapSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/hesaplar/${id}`)),
    virman: (g: Record<string, unknown>) => istek<Hareket>('POST', u('/virman'), g),
    kategoriler: () => istek<{ items: Kategori[] }>('GET', u('/kategoriler')),
    kategoriEkle: (g: Record<string, unknown>) => istek<Kategori>('POST', u('/kategoriler'), g),
    kategoriGuncelle: (id: number, g: Record<string, unknown>) => istek<Kategori>('PUT', u(`/kategoriler/${id}`), g),
    kategoriSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/kategoriler/${id}`)),
    varsayilanKategoriler: () => istek<{ eklenen: number }>('POST', u('/kategoriler/varsayilanlar'), {}),
    hareketler: (q: HareketSuzgeci = {}) =>
      istek<{ items: Hareket[]; toplam: number; sayfa: number; adet: number; toplamlar: Toplam[] }>('GET', u('/hareketler', q as Sorgu)),
    hareket: (id: number) => istek<Hareket>('GET', u(`/hareketler/${id}`)),
    hareketEkle: (g: Record<string, unknown>) => istek<Hareket>('POST', u('/hareketler'), g),
    hareketGuncelle: (id: number, g: Record<string, unknown>) => istek<Hareket>('PUT', u(`/hareketler/${id}`), g),
    hareketSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/hareketler/${id}`)),
    hareketCsv: (q: HareketSuzgeci = {}) => indir('/hareketler.csv', q as Sorgu, 'hareketler.csv'),
    hareketPdf: (q: HareketSuzgeci & { dil?: string } = {}) => indir('/hareketler.pdf', q as Sorgu, 'hareketler.pdf'),
    async ekYukle(id: number, dosya: File): Promise<{ id: number; ad: string }> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(u(`/hareketler/${id}/ekler`), { method: 'POST', body: form });
      return y.json();
    },
    ekIndir: (id: number, ad: string) => indir(`/ekler/${id}`, {}, ad),
    ekSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/ekler/${id}`)),
    csvOnizle: (csv: string) => istek<CsvOnizleme>('POST', u('/ice-aktar/onizle'), { csv }),
    iceAktar: (g: Record<string, unknown>) => istek<IceAktarSonucu>('POST', u('/ice-aktar'), g),
    tekrarlar: () => istek<{ items: Tekrar[] }>('GET', u('/tekrarlar')),
    tekrarEkle: (g: Record<string, unknown>) => istek<Tekrar>('POST', u('/tekrarlar'), g),
    tekrarGuncelle: (id: number, g: Record<string, unknown>) => istek<Tekrar>('PUT', u(`/tekrarlar/${id}`), g),
    tekrarSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/tekrarlar/${id}`)),
    cariler: (q: { ara?: string; tur?: string; arsiv?: boolean } = {}) =>
      istek<{ items: Cari[]; toplamlar: { para_birimi: string; alacak: number; borc: number }[] }>('GET', u('/cariler', q)),
    cari: (id: number) => istek<CariAyrinti>('GET', u(`/cariler/${id}`)),
    cariEkle: (g: Record<string, unknown>) => istek<Cari>('POST', u('/cariler'), g),
    cariGuncelle: (id: number, g: Record<string, unknown>) => istek<Cari>('PUT', u(`/cariler/${id}`), g),
    cariSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/cariler/${id}`)),
    baglantiAdaylari: (ara: string) => istek<{ items: BaglantiAdayi[] }>('GET', u('/cariler/baglanti-adaylari', { ara })),
    ekstre: (id: number, bas: string, bit: string) => istek<Ekstre>('GET', u(`/cariler/${id}/ekstre`, { bas, bit })),
    ekstrePdf: (id: number, bas: string, bit: string, dil: string) => indir(`/cariler/${id}/ekstre.pdf`, { bas, bit, dil }, `cari-ekstre-${id}.pdf`),
    ekstreCsv: (id: number, bas: string, bit: string) => indir(`/cariler/${id}/ekstre.csv`, { bas, bit }, `cari-ekstre-${id}.csv`),
    yaslandirma: (yon: 'alacak' | 'borc') => istek<Yaslandirma>('GET', u('/yaslandirma', { yon })),
    butceler: (ay: string) => istek<ButceDurumu>('GET', u('/butceler', { ay })),
    butceYaz: (g: { kategori_id: number; ay: string; tutar: string | null; para_birimi: string }) =>
      istek<{ ok: boolean; butce_asimi?: number }>('PUT', u('/butceler'), g),
    raporAylik: (yil: number) => istek<AylikRapor>('GET', u('/raporlar/aylik', { yil })),
    raporKategori: (bas: string, bit: string, tur: KategoriTuru) => istek<KategoriRaporu>('GET', u('/raporlar/kategori', { bas, bit, tur })),
    raporKarZarar: (bas: string, bit: string) => istek<KarZarar>('GET', u('/raporlar/kar-zarar', { bas, bit })),
    raporNakit: (ay = 6) => istek<NakitAkisi>('GET', u('/raporlar/nakit-akisi', { ay })),
    raporKdv: (yil: number) => istek<KdvRaporu>('GET', u('/raporlar/kdv', { yil })),
    raporCsv: (tur: 'aylik' | 'kategori' | 'kdv' | 'nakit' | 'kar_zarar', q: Sorgu = {}) => indir('/raporlar.csv', { tur, ...q }, `${tur}.csv`),
  };
}

export type MuhasebeApi = ReturnType<typeof muhasebeApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof MuhasebeHatasi) {
    return t(`onMuhasebe.hata.${e.kod}`, { ...e.ek, defaultValue: t('onMuhasebe.hata.genel') }) as string;
  }
  return t('onMuhasebe.hata.genel');
}

// ---------------------------------------------------------------------------
// Biçim
// ---------------------------------------------------------------------------
function yerelAd(dil: string): string {
  return dil === 'ar' ? 'ar-u-nu-latn' : dil;
}

/** Kuruş → para metni (para birimine göre). */
export function para(kurus: number | null | undefined, birim: string, dil: string): string {
  const tutar = (kurus || 0) / 100;
  try {
    return new Intl.NumberFormat(yerelAd(dil), { style: 'currency', currency: birim || 'TRY', currencyDisplay: 'narrowSymbol' }).format(tutar);
  } catch {
    return `${tutar.toFixed(2)} ${birim}`;
  }
}

/** Kuruş → girdi alanı metni ("1250,50"; Türkçe ondalık virgül). */
export function kurusMetni(kurus: number | null | undefined): string {
  if (kurus === null || kurus === undefined) return '';
  const eksi = kurus < 0;
  const a = Math.abs(kurus);
  return `${eksi ? '-' : ''}${Math.floor(a / 100)},${String(a % 100).padStart(2, '0')}`;
}

export function sayiYaz(n: number | null | undefined, dil: string, kesir = 1): string {
  if (n === null || n === undefined) return '—';
  try {
    return new Intl.NumberFormat(yerelAd(dil), { maximumFractionDigits: kesir }).format(n);
  } catch {
    return String(n);
  }
}

/** "2026-10-05" → yerel gün (saat dilimi kaymadan). */
export function gunYaz(iso: string | null | undefined, dil: string, secenek: Intl.DateTimeFormatOptions = { dateStyle: 'medium' }): string {
  if (!iso) return '—';
  const [y, a, g] = iso.slice(0, 10).split('-').map(Number);
  try {
    return new Intl.DateTimeFormat(yerelAd(dil), { ...secenek, timeZone: 'UTC' }).format(new Date(Date.UTC(y, a - 1, g)));
  } catch {
    return iso.slice(0, 10);
  }
}

/** "2026-10" → "Eki 2026" (kısa ay adı). */
export function ayYaz(ay: string, dil: string, bicim: 'short' | 'long' = 'short'): string {
  const [y, a] = ay.split('-').map(Number);
  try {
    return new Intl.DateTimeFormat(yerelAd(dil), { month: bicim, year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(y, a - 1, 1)));
  } catch {
    return ay;
  }
}

export function ayEkle(ay: string, n: number): string {
  const [y, a] = ay.split('-').map(Number);
  const toplam = y * 12 + (a - 1) + n;
  return `${String(Math.floor(toplam / 12)).padStart(4, '0')}-${String((toplam % 12) + 1).padStart(2, '0')}`;
}

/** Kategorinin görünen adı: varsayılan setten geliyor ve adı değişmediyse seçili dilde. */
export function kategoriAdi(t: TFunction, k: { ad: string | null; anahtar: string | null; ad_degisti: boolean } | null | undefined): string {
  if (!k) return t('onMuhasebe.kategorisiz');
  if (k.anahtar && !k.ad_degisti) return t(`onMuhasebe.kategori.${k.anahtar}`, { defaultValue: k.ad || '' }) as string;
  return k.ad || t('onMuhasebe.kategorisiz');
}

export const TUR_RENGI: Record<HareketTuru, string> = {
  gelir: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  gider: 'border-rose-400/40 bg-rose-500/15 text-rose-200',
  tahsilat: 'border-sky-400/40 bg-sky-500/15 text-sky-200',
  odeme: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  virman: 'border-violet-400/40 bg-violet-500/15 text-violet-200',
};

/** Hareketin hesap/kasa bakiyesine işareti (gösterim için). */
export function isaret(h: Pick<Hareket, 'tur'>): 1 | -1 | 0 {
  if (h.tur === 'gelir' || h.tur === 'tahsilat') return 1;
  if (h.tur === 'gider' || h.tur === 'odeme') return -1;
  return 0;
}

/** Ortak girdi sınıfında `w-full` yerine dar genişlik. */
export const dar = (sinif: string, genislik: string) => sinif.replace('w-full', genislik);

/** Bölüm bileşenlerinin ortak özellikleri (sarmalayıcı `OnMuhasebe.tsx`). */
export interface BolumProps {
  api: MuhasebeApi;
  meta: Meta;
  /** Meta (hesaplar, kategoriler) + açık bölüm yeniden yüklenir. */
  yenile: () => void;
  /** Sarmalayıcıda bir şey değişince artar (eşitleme sonrası yeniden yükleme için). */
  surum: number;
  git: (bolum: 'ozet' | 'hareketler' | 'hesaplar' | 'cariler' | 'tekrarlar' | 'butce' | 'raporlar' | 'ayarlar') => void;
}

/** Bugün (İstanbul) "YYYY-AA-GG". */
export function bugun(): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}
