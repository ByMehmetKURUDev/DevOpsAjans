import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 5M — E-posta pazarlama: panel uçları.
 *
 * Yönetici `/api/v1/eposta-pazarlama/yonetim/...` (ajansın kendi hesabı), müşteri
 * `/api/v1/eposta-pazarlamam/...` (etkin hesap `X-MK-Hesap` başlığıyla). İki panel aynı
 * bileşeni kullanıyor; yalnız taban yol değişiyor. Bu dosya yalnız sekme açıldığında iniyor.
 */

export type PazarlamaMod = 'yonetici' | 'musteri';
export type AliciTuru = 'bireysel' | 'kurumsal';
export type IzinDurumu = 'izinli' | 'izinsiz' | 'bekliyor' | 'reddetti';
export type Hiza = 'sol' | 'orta' | 'sag';

export type Blok =
  | { tur: 'logo'; hiza?: Hiza }
  | { tur: 'baslik'; metin: string; seviye?: 1 | 2; hiza?: Hiza }
  | { tur: 'metin'; metin: string; hiza?: Hiza }
  | { tur: 'gorsel'; url: string; alt?: string; baglanti?: string; genislik?: number; hiza?: Hiza }
  | { tur: 'dugme'; metin: string; url: string; hiza?: Hiza }
  | { tur: 'ayirici' }
  | { tur: 'bosluk'; yukseklik?: number }
  | { tur: 'iki_sutun'; sol: Blok[]; sag: Blok[] };
export type BlokTuru = Blok['tur'];

export interface Meta {
  yonetici: boolean;
  hesap: string | null;
  resend_kurulu: boolean;
  sahte_mod: boolean;
  kimlik: { gonderen_adi: string; unvan: string; adres: string; eksik: string[]; yanit_adresi: string; kaynak: string };
  gonderen_adresi: string;
  sinirlar: { aylik: number | null; kullanilan: number; kisi: number | null; kisi_sayisi: number; gunluk_kisi: number };
  yer_tutucular: string[];
  blok_turleri: BlokTuru[];
  segment_alanlari: string[];
  segment_oplari: Record<string, string[]>;
  tetikler: string[];
  diller: string[];
  form_betigi: string;
  csv_sutunlari: string[];
  webhook?: { adres: string; imza_tanimli: boolean; ortam_degiskeni: string };
}

export interface Ayarlar {
  gonderen_adi: string;
  yanit_adresi: string;
  unvan: string;
  adres: string;
  logo_url: string;
  marka_rengi: string;
  dil: string;
  iys_durumu: 'bilinmiyor' | 'var' | 'yok';
  iys_marka_kodu: string;
  acilma_takibi: boolean;
  tiklama_takibi: boolean;
  gunluk_kisi_siniri: number;
  askida: boolean;
  askida_neden: string | null;
  askida_at: string | null;
}

export interface Kisi {
  id: number;
  eposta: string;
  ad: string | null;
  firma: string | null;
  alici_turu: AliciTuru;
  izin_durumu: IzinDurumu;
  izin_kaynagi: string | null;
  izin_zamani: string | null;
  izin_metin_surumu: string | null;
  izin_kaniti: string | null;
  onay_zamani: string | null;
  ret_zamani: string | null;
  ret_kaynagi: string | null;
  kaynak: string;
  etiketler: string[];
  ozel_alanlar: Record<string, string>;
  dil: string;
  son_etkilesim_at: string | null;
  son_gonderim_at: string | null;
  created_at: string | null;
  bastirilmis?: boolean;
  listeler?: number[];
}

export interface Liste {
  id: number;
  ad: string;
  aciklama: string;
  aktif: number;
  bekliyor: number;
  cikti: number;
}

export interface Form {
  id: number;
  liste_id: number;
  ad: string;
  genel_anahtar: string;
  baslik: string;
  aciklama: string;
  dil: string;
  ad_sor: boolean;
  tur_sor: boolean;
  tesekkur_metni: string;
  aydinlatma_baglantisi: string;
  izinli_alanlar: string[];
  aktif: boolean;
  gonderim_sayisi: number;
  adres: string;
  gomme_kodu: string;
}

export interface SegmentKurali {
  alan: string;
  op: string;
  deger?: string | number;
  anahtar?: string;
}
export interface Segment {
  id: number;
  ad: string;
  kurallar: { birlesim: 've' | 'veya'; kurallar: SegmentKurali[] };
  sayi: number | null;
}

export interface Hedef {
  listeler: number[];
  segmentler: number[];
  haric_listeler: number[];
}
export interface AbAyari {
  acik: boolean;
  konu_b?: string;
  oran?: number;
  bekleme_saat?: number;
  olcut?: 'acilma' | 'tiklama';
}
export interface Istatistik {
  satir: number;
  gonderilen: number;
  teslim: number;
  geri_donen: number;
  sikayet: number;
  ret: number;
  acilan: number;
  tiklayan: number;
}
export type KampanyaDurumu = 'taslak' | 'zamanlandi' | 'gonderiliyor' | 'ab_test' | 'duraklatildi' | 'tamamlandi' | 'iptal';
export interface Kampanya {
  id: number;
  ad: string;
  konu: string;
  onizleme_metni: string;
  gonderen_adi: string;
  yanit_adresi: string;
  dil: string;
  bloklar: Blok[];
  hedef: Hedef;
  ab: AbAyari;
  durum: KampanyaDurumu;
  zamanlanan_at: string | null;
  baslangic_at: string | null;
  bitis_at: string | null;
  kazanan: 'a' | 'b' | null;
  duraklatma_nedeni: string | null;
  hedef_sayisi: number;
  takip_acilma: boolean;
  takip_tiklama: boolean;
  istatistik?: Istatistik | null;
}
export interface KitleOzeti {
  toplam: number;
  gonderilebilir: number;
  atlanacak: Record<string, number>;
  kota_kalan?: number | null;
}
export interface Rapor {
  kampanya: Kampanya;
  sayilar: Istatistik & { atlanan: number; hata: number; bekleyen: number };
  oranlar: Record<'teslim' | 'geri_donme' | 'sikayet' | 'ret' | 'acilma' | 'tiklama', number | null>;
  atlama_nedenleri: Record<string, number>;
  varyantlar: Record<string, Istatistik>;
  baglantilar: { indeks: number; url: string; tiklama: number }[];
  alicilar: { eposta: string | null; durum: string; neden: string | null; varyant: string | null; gonderim_at: string | null }[];
}
export interface Onizleme {
  html: string;
  metin: string;
  konu: string;
  gonderen: string;
  baglantilar: string[];
  kimlik_eksik: string[];
}

export interface DiziAdimi {
  id?: number;
  sira?: number;
  bekle_gun: number;
  bekle_saat: number;
  konu: string;
  onizleme_metni: string;
  bloklar: Blok[];
}
export interface Dizi {
  id: number;
  ad: string;
  tetik: 'liste_katildi' | 'abonelik_onaylandi';
  liste_id: number | null;
  aktif: boolean;
  cikis: { hedef: null | { tur: 'tiklama' } | { tur: 'etiket'; deger: string } | { tur: 'liste'; liste_id: number } };
  gonderen_adi: string;
  dil: string;
  adimlar: DiziAdimi[];
  kayitlar?: Record<string, number>;
}
export interface Ozet {
  kisiler: { toplam: number; izin: Record<string, number>; tur: Record<string, number>; bastirilan: number };
  son_30_gun: { gonderilen: number; sikayet: number; geri_donen: number };
  son_kampanyalar: Kampanya[];
}
export interface HesapSagligi {
  kapsam: string;
  hesap: string | null;
  kisi: number;
  gonderilen_30: number;
  sikayet_30: number;
  geri_donen_30: number;
  askida: boolean;
  askida_neden: string | null;
  aylik_kullanim: number;
}
export interface IceAktarmaOnizleme {
  ozet: { gecerli: number; hatali: number; izinli: number; izinsiz: number; izinsiz_bireysel: number; kurumsal: number; mevcut: number; bastirilan: number };
  ornek: { satir: number; eposta: string; ad: string | null; alici_turu: AliciTuru; izinli: boolean; izin_kaynagi: string | null }[];
  hatalar: { satir: number; kod: string; deger: string }[];
}

export class PazarlamaHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): PazarlamaHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new PazarlamaHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new PazarlamaHatasi(durum, 'cok_hizli');
  if (durum === 404) return new PazarlamaHatasi(durum, 'bulunamadi');
  if (durum === 403) return new PazarlamaHatasi(durum, 'yetki');
  return new PazarlamaHatasi(durum, durum === 0 ? 'ag' : 'genel');
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

async function formIstegi<T>(url: string, form: FormData): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, { method: 'POST', body: form, headers: oturumBasliklari() });
  } catch {
    throw new PazarlamaHatasi(0, 'ag');
  }
  const govde = (await yanit.json().catch(() => null)) as (T & { detail?: unknown }) | null;
  if (!yanit.ok) throw hataCoz(yanit.status, govde?.detail);
  return govde as T;
}

export function pazarlamaApi(mod: PazarlamaMod) {
  const T = mod === 'yonetici' ? '/api/v1/eposta-pazarlama/yonetim' : '/api/v1/eposta-pazarlamam';
  const q = (o: Record<string, string | number | undefined | null>) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
    const s = p.toString();
    return s ? `?${s}` : '';
  };
  return {
    meta: () => istek<Meta>('GET', `${T}/meta`),
    ozet: () => istek<Ozet>('GET', `${T}/ozet`),
    ayarlar: () => istek<Ayarlar>('GET', `${T}/ayarlar`),
    ayarlarYaz: (g: Partial<Ayarlar>) => istek<Ayarlar>('PUT', `${T}/ayarlar`, g),
    kisiler: (f: { ara?: string; liste_id?: number; izin?: string; tur?: string; kaynak?: string; sinir?: number; atla?: number } = {}) =>
      istek<{ items: Kisi[]; toplam: number }>('GET', `${T}/kisiler${q(f)}`),
    kisi: (id: number) => istek<Kisi & { uyelikler: { liste_id: number; durum: string }[] }>('GET', `${T}/kisiler/${id}`),
    kisiEkle: (g: Record<string, unknown>) => istek<Kisi>('POST', `${T}/kisiler`, g),
    kisiGuncelle: (id: number, g: Record<string, unknown>) => istek<Kisi>('PUT', `${T}/kisiler/${id}`, g),
    kisiRet: (id: number) => istek<Kisi>('POST', `${T}/kisiler/${id}/ret`),
    kisiSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/kisiler/${id}`),
    iceAktarOnizleme(dosya: File, varsayilanTur: AliciTuru): Promise<IceAktarmaOnizleme> {
      const f = new FormData();
      f.append('dosya', dosya);
      f.append('varsayilan_tur', varsayilanTur);
      return formIstegi(`${T}/kisiler/ice-aktar/onizleme`, f);
    },
    iceAktar(dosya: File, g: { liste_id?: number | null; varsayilan_tur: AliciTuru; kaynak_notu: string }) {
      const f = new FormData();
      f.append('dosya', dosya);
      if (g.liste_id) f.append('liste_id', String(g.liste_id));
      f.append('varsayilan_tur', g.varsayilan_tur);
      f.append('kaynak_notu', g.kaynak_notu);
      return formIstegi<{ sayilar: Record<string, number> }>(`${T}/kisiler/ice-aktar`, f);
    },
    crmAktar: (g: { liste_id?: number | null; alici_turu: AliciTuru; yalniz_izinli: boolean }) =>
      istek<{ sayilar: Record<string, number> }>('POST', `${T}/kisiler/crm-aktar`, g),
    bastirma: (ara?: string) =>
      istek<{ items: { id: number; eposta: string; neden: string; kaynak: string | null; created_at: string | null }[]; toplam: number }>(
        'GET',
        `${T}/bastirma${q({ ara })}`
      ),
    bastirmaEkle: (eposta: string) => istek<{ ok: boolean; eklendi: boolean }>('POST', `${T}/bastirma`, { eposta }),
    bastirmaSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/bastirma/${id}`),
    listeler: () => istek<{ items: Liste[] }>('GET', `${T}/listeler`),
    listeEkle: (g: { ad: string; aciklama?: string }) => istek<Liste>('POST', `${T}/listeler`, g),
    listeGuncelle: (id: number, g: { ad?: string; aciklama?: string }) => istek<Liste>('PUT', `${T}/listeler/${id}`, g),
    listeSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/listeler/${id}`),
    formlar: () => istek<{ items: Form[] }>('GET', `${T}/formlar`),
    formEkle: (g: Partial<Form>) => istek<Form>('POST', `${T}/formlar`, g),
    formGuncelle: (id: number, g: Partial<Form>) => istek<Form>('PUT', `${T}/formlar/${id}`, g),
    formSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/formlar/${id}`),
    segmentler: () => istek<{ items: Segment[] }>('GET', `${T}/segmentler`),
    segmentOnizleme: (kurallar: Segment['kurallar']) =>
      istek<{ sayi: number; ornek: { id: number; eposta: string; ad: string | null }[] }>('POST', `${T}/segmentler/onizleme`, { kurallar }),
    segmentEkle: (g: { ad: string; kurallar: Segment['kurallar'] }) => istek<Segment>('POST', `${T}/segmentler`, g),
    segmentGuncelle: (id: number, g: { ad?: string; kurallar?: Segment['kurallar'] }) => istek<Segment>('PUT', `${T}/segmentler/${id}`, g),
    segmentSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/segmentler/${id}`),
    gorselYukle(dosya: File) {
      const f = new FormData();
      f.append('dosya', dosya);
      return formIstegi<{ url: string; genislik: number; yukseklik: number }>(`${T}/gorseller`, f);
    },
    onizleme: (g: { bloklar: Blok[]; konu: string; onizleme_metni?: string; dil: string; gonderen_adi?: string }) =>
      istek<Onizleme>('POST', `${T}/onizleme`, g),
    kampanyalar: () => istek<{ items: Kampanya[] }>('GET', `${T}/kampanyalar`),
    kampanya: (id: number) => istek<Kampanya>('GET', `${T}/kampanyalar/${id}`),
    kampanyaEkle: (g: Partial<Kampanya>) => istek<Kampanya>('POST', `${T}/kampanyalar`, g),
    kampanyaGuncelle: (id: number, g: Partial<Kampanya>) => istek<Kampanya>('PUT', `${T}/kampanyalar/${id}`, g),
    kampanyaSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/kampanyalar/${id}`),
    kampanyaKopyala: (id: number) => istek<Kampanya>('POST', `${T}/kampanyalar/${id}/kopyala`),
    kitle: (id: number, hedef?: Hedef) => istek<KitleOzeti>('POST', `${T}/kampanyalar/${id}/kitle`, hedef ? { hedef } : {}),
    test: (id: number, adresler: string[]) =>
      istek<{ sonuc: { adres: string; durum: string; hata: string | null }[] }>('POST', `${T}/kampanyalar/${id}/test`, { adresler }),
    gonder: (id: number, zaman?: string | null) =>
      istek<{ kampanya: Kampanya; kitle: KitleOzeti }>('POST', `${T}/kampanyalar/${id}/gonder`, zaman ? { zaman } : {}),
    durdur: (id: number) => istek<Kampanya>('POST', `${T}/kampanyalar/${id}/durdur`),
    devam: (id: number) => istek<Kampanya>('POST', `${T}/kampanyalar/${id}/devam`),
    rapor: (id: number) => istek<Rapor>('GET', `${T}/kampanyalar/${id}/rapor`),
    diziler: () => istek<{ items: Dizi[] }>('GET', `${T}/diziler`),
    diziEkle: (g: Partial<Dizi>) => istek<Dizi>('POST', `${T}/diziler`, g),
    diziGuncelle: (id: number, g: Partial<Dizi>) => istek<Dizi>('PUT', `${T}/diziler/${id}`, g),
    diziSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/diziler/${id}`),
    diziRapor: (id: number) =>
      istek<{ adimlar: { id: number; sira: number; konu: string; gonderilen: number; acilan: number; tiklayan: number }[]; kayitlar: Record<string, number>; cikis: Record<string, number> }>(
        'GET',
        `${T}/diziler/${id}/rapor`
      ),
    hesaplar: () => istek<{ items: HesapSagligi[] }>('GET', `${T}/hesaplar`),
    hesapAskida: (kapsam: string, askida: boolean) => istek<Ayarlar>('PUT', `${T}/hesaplar/${encodeURIComponent(kapsam)}`, { askida }),
  };
}

export type PazarlamaApi = ReturnType<typeof pazarlamaApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof PazarlamaHatasi) {
    return t(`epostaPazarlama.hata.${e.kod}`, { ...e.ek, defaultValue: t('epostaPazarlama.hata.genel') }) as string;
  }
  return t('epostaPazarlama.hata.genel');
}

export function tarihYaz(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function yuzde(oran: number | null | undefined, dil: string): string {
  if (oran === null || oran === undefined) return '—';
  try {
    return new Intl.NumberFormat(dil, { style: 'percent', maximumFractionDigits: 1 }).format(oran);
  } catch {
    return `${Math.round(oran * 1000) / 10}%`;
  }
}
