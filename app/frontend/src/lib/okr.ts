import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 6O — Hedefler ve OKR: panel uçları ve küçük yardımcılar.
 *
 * Müşteri paneli `/api/v1/okr/...` (etkin hesap `X-MK-Hesap`), ajans paneli `/api/v1/okr-yonetim/...` (ajansın KENDİ
 * OKR'ları). Müşteriyle paylaşılan ajans hedefleri `/api/v1/okr-paylasilan` (salt okunur kart). Para değerleri kuruş.
 * İlerleme sunucuda hesaplanır (tek yer: `services/okr.py`); burada yalnız gösterim. Bu dosya sekme açılınca (lazy) iner.
 */

export type OkrMod = 'musteri' | 'yonetici';
export type DonemTuru = 'ceyrek' | 'yil' | 'ozel';
export type KrTuru = 'sayi' | 'yuzde' | 'para' | 'evet_hayir' | 'kilometre';
export type Yon = 'artir' | 'azalt';
export type Guven = 'yolunda' | 'riskli' | 'tehlikede';
export type IlerlemeDurumu = 'tamam' | 'yolunda' | 'riskli' | 'geride';
export type HedefDurumu = 'taslak' | 'etkin' | 'kapandi';
export type Gorunurluk = 'ekip' | 'ozel';

export interface Donem {
  id: number;
  ad: string;
  tur: DonemTuru;
  yil: number | null;
  ceyrek: number | null;
  baslangic: string;
  bitis: string;
  etkin: boolean;
  durum: 'acik' | 'kapandi';
  kapanis_notu: string;
  kapandi_at: string | null;
  kapatan: string | null;
  beklenen: number;
  etiket: string;
}

export interface KilometreTasi {
  id: string;
  metin: string;
  tamam: boolean;
}

export interface Checkin {
  id: number;
  kr_id: number;
  tur: 'elle' | 'otomatik' | 'odak';
  deger: number;
  onceki: number | null;
  guven: Guven | null;
  notlar: string;
  sure_dk: number | null;
  tarih: string;
  yazan: string | null;
  zaman: string | null;
}

export interface TasimaGecmisi {
  kr_id: number;
  hedef_id: number;
  donem_id: number | null;
  donem: string | null;
  ilerleme: number;
  kapanis_puani: number | null;
  checkin_sayisi: number;
}

export interface Kr {
  id: number;
  hedef_id: number;
  baslik: string;
  tur: KrTuru;
  birim: string;
  para_birimi: string | null;
  baslangic: number;
  hedef: number;
  mevcut: number;
  yon: Yon;
  ilerleme: number;
  kilometre_tamam: number;
  kilometre_toplam: number;
  agirlik: number;
  sahip: string;
  kilometre_taslari: KilometreTasi[];
  kaynak: string | null;
  kaynak_ayar: { para_birimi?: string; proje_id?: number };
  kaynak_son_yenileme: string | null;
  kaynak_hata: string | null;
  guven: Guven | null;
  son_checkin_at: string | null;
  kapanis_puani: number | null;
  tasindi_kaynak_id: number | null;
  sira: number;
  checkinler?: Checkin[];
  tasima_gecmisi?: TasimaGecmisi[];
  onerilen_puan?: number;
  acik?: boolean;
}

export interface Hedef {
  id: number;
  donem_id: number;
  baslik: string;
  aciklama: string;
  ilerleme: number | null;
  durum_rengi: IlerlemeDurumu | null;
  krler: Kr[];
  sahip: string;
  ust_id: number | null;
  gorunurluk: Gorunurluk;
  durum: HedefDurumu;
  musteri_email: string | null;
  musteri_paylasim: boolean;
  tamamlandi_at: string | null;
  tasindi_kaynak_id: number | null;
  olusturan: string | null;
  kr_sayisi: number;
}

export interface HedefAyrinti extends Hedef {
  donem: Donem;
  ust: { id: number; baslik: string } | null;
  altlar: { id: number; baslik: string }[];
}

export interface DonemOzeti {
  donem: Donem;
  hedefler: Hedef[];
  ilerleme: number | null;
  durum_rengi: IlerlemeDurumu | null;
}

export interface Kapanis extends DonemOzeti {
  hedef_donemler: Donem[];
}

export interface Kaynak {
  anahtar: string;
  tur: KrTuru;
  para: boolean;
  proje: boolean;
  modul: string | null;
}

export interface AgacDugumu {
  id: number;
  baslik: string;
  ust_id: number | null;
  donem_id: number;
  donem: string | null;
  ilerleme: number | null;
  durum_rengi: IlerlemeDurumu | null;
  sahip: string;
  durum: HedefDurumu;
  gorunurluk: Gorunurluk;
  kr_sayisi: number;
  secili_donemde: boolean;
}

export interface Meta {
  yonetici: boolean;
  ajans: boolean;
  hesap: string | null;
  kisi: string;
  okur: boolean;
  bugun: string;
  ai_hazir: boolean;
  hedef_siniri: number | null;
  kaynaklar: Kaynak[];
  projeler: { id: number; ad: string; musteri: string | null }[];
  musteri_hesaplari: { eposta: string; ad: string | null }[];
  ekip: { email: string; ad: string | null }[];
  donemler: Donem[];
  etkin_donem_id: number | null;
  sabitler: {
    donem_turleri: DonemTuru[];
    kr_turleri: KrTuru[];
    yonler: Yon[];
    guvenler: Guven[];
    gorunurlukler: Gorunurluk[];
    para_birimleri: string[];
    en_cok_kr: number;
    en_cok_agirlik: number;
    hatirlatma_gun: number;
    odak_dk: number;
    mola_dk: number;
  };
}

export interface KrOnerisi {
  baslik: string;
  tur: KrTuru;
  baslangic: number;
  hedef: number;
  yon: Yon;
  birim: string | null;
  gerekce?: string | null;
}

export interface PaylasilanHedef {
  id: number;
  baslik: string;
  aciklama: string;
  ilerleme: number | null;
  durum_rengi: IlerlemeDurumu | null;
  krler: (Pick<Kr, 'id' | 'baslik' | 'tur' | 'birim' | 'para_birimi' | 'baslangic' | 'hedef' | 'mevcut' | 'yon' | 'ilerleme' | 'kilometre_tamam' | 'kilometre_toplam'> & {
    kilometre_taslari?: { metin: string; tamam: boolean }[];
  })[];
  donem: { etiket: string; tur: DonemTuru; yil: number | null; ceyrek: number | null; ad: string; baslangic: string; bitis: string; beklenen: number; durum: string };
  kapandi: boolean;
}

export class OkrHatasi extends Error {
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

function hataCoz(durum: number, detay: unknown): OkrHatasi {
  if (detay && typeof detay === 'object' && 'kod' in (detay as Record<string, unknown>)) {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new OkrHatasi(durum, String(kod), ek);
  }
  if (durum === 429) return new OkrHatasi(durum, 'cok_hizli');
  if (durum === 404) return new OkrHatasi(durum, 'bulunamadi');
  if (durum === 403) return new OkrHatasi(durum, 'yetki_yok');
  return new OkrHatasi(durum, durum === 0 ? 'ag' : 'genel');
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

async function indir(url: string, ad: string): Promise<void> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, { headers: oturumBasliklari() });
  } catch {
    throw new OkrHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = (await yanit.json().catch(() => null)) as { detail?: unknown } | null;
    throw hataCoz(yanit.status, govde?.detail);
  }
  const blob = await yanit.blob();
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

export function okrApi(mod: OkrMod) {
  const T = mod === 'yonetici' ? '/api/v1/okr-yonetim' : '/api/v1/okr';
  const u = (yol: string, q?: Record<string, string | number | undefined | null>) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(q || {})) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
    const s = p.toString();
    return `${T}${yol}${s ? `?${s}` : ''}`;
  };
  type G = Record<string, unknown>;
  return {
    mod,
    meta: () => istek<Meta>('GET', u('/meta')),
    donemler: () => istek<{ items: Donem[] }>('GET', u('/donemler')),
    donemEkle: (g: G) => istek<Donem>('POST', u('/donemler'), g),
    donemGuncelle: (id: number, g: G) => istek<Donem>('PUT', u(`/donemler/${id}`), g),
    donemSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/donemler/${id}`)),
    donemOzeti: (id: number) => istek<DonemOzeti>('GET', u(`/donemler/${id}/ozet`)),
    donemYenile: (id: number) => istek<{ yenilenen: number; degisen: number; hatali: number }>('POST', u(`/donemler/${id}/yenile`), {}),
    kapanis: (id: number) => istek<Kapanis>('GET', u(`/donemler/${id}/kapanis`)),
    kapat: (id: number, g: G) =>
      istek<{ ok: boolean; tasinan_hedef: number; tasinan_kr: number; hedef_donem_id: number | null }>('POST', u(`/donemler/${id}/kapat`), g),
    raporPdf: (id: number, dil: string) => indir(u(`/donemler/${id}/rapor.pdf`, { dil }), `okr-${id}.pdf`),
    raporCsv: (id: number, dil: string) => indir(u(`/donemler/${id}/rapor.csv`, { dil }), `okr-${id}.csv`),
    agac: (donemId?: number | null) => istek<{ items: AgacDugumu[] }>('GET', u('/agac', { donem_id: donemId ?? undefined })),
    hedefEkle: (g: G) => istek<Hedef>('POST', u('/hedefler'), g),
    hedef: (id: number) => istek<HedefAyrinti>('GET', u(`/hedefler/${id}`)),
    hedefGuncelle: (id: number, g: G) => istek<Hedef>('PUT', u(`/hedefler/${id}`), g),
    hedefSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/hedefler/${id}`)),
    krEkle: (hedefId: number, g: G) => istek<Kr>('POST', u(`/hedefler/${hedefId}/krler`), g),
    krGuncelle: (id: number, g: G) => istek<Kr>('PUT', u(`/krler/${id}`), g),
    krSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/krler/${id}`)),
    checkin: (id: number, g: G) => istek<{ kr: Kr; checkin: Checkin }>('POST', u(`/krler/${id}/checkin`), g),
    checkinler: (id: number) => istek<{ items: Checkin[]; tasima_gecmisi: TasimaGecmisi[] }>('GET', u(`/krler/${id}/checkinler`)),
    krYenile: (id: number) => istek<{ kr: Kr; degisti: boolean; hata: string | null }>('POST', u(`/krler/${id}/yenile`), {}),
    odak: (id: number, g: G) => istek<{ checkin: Checkin }>('POST', u(`/krler/${id}/odak`), g),
    krOner: (g: G) => istek<{ oneriler: KrOnerisi[] }>('POST', u('/ai/kr-oner'), g),
  };
}

export type OkrApi = ReturnType<typeof okrApi>;

export function paylasilanHedefler(): Promise<{ items: PaylasilanHedef[] }> {
  return istek<{ items: PaylasilanHedef[] }>('GET', '/api/v1/okr-paylasilan');
}

/** Hata → seçili dilde metin (bilinmeyen kod → genel). Ek paket `hedefler` ya da `hedefKarti`. */
export function hataMetni(t: TFunction, e: unknown, onek = 'hedefler'): string {
  if (e instanceof OkrHatasi) {
    return t(`${onek}.hata.${e.kod}`, { ...e.ek, defaultValue: t(`${onek}.hata.genel`) }) as string;
  }
  return t(`${onek}.hata.genel`);
}

// ---------------------------------------------------------------------------
// Biçim
// ---------------------------------------------------------------------------
function yerelAd(dil: string): string {
  return dil === 'ar' ? 'ar-u-nu-latn' : dil;
}

export function sayiYaz(n: number | null | undefined, dil: string, kesir = 2): string {
  if (n === null || n === undefined) return '—';
  try {
    return new Intl.NumberFormat(yerelAd(dil), { maximumFractionDigits: kesir }).format(n);
  } catch {
    return String(n);
  }
}

export function para(kurus: number | null | undefined, birim: string | null | undefined, dil: string): string {
  const tutar = (kurus || 0) / 100;
  try {
    return new Intl.NumberFormat(yerelAd(dil), { style: 'currency', currency: birim || 'TRY', currencyDisplay: 'narrowSymbol', maximumFractionDigits: 2 }).format(tutar);
  } catch {
    return `${tutar.toFixed(2)} ${birim || ''}`.trim();
  }
}

export function yuzde(oran: number | null | undefined, dil: string): string {
  if (oran === null || oran === undefined) return '—';
  try {
    return new Intl.NumberFormat(yerelAd(dil), { style: 'percent', maximumFractionDigits: 0 }).format(oran);
  } catch {
    return `${Math.round(oran * 100)}%`;
  }
}

/** KR değeri (türüne göre). */
export function degerYaz(kr: Pick<Kr, 'tur' | 'para_birimi' | 'birim'>, deger: number | null | undefined, dil: string, t: TFunction): string {
  if (deger === null || deger === undefined) return '—';
  if (kr.tur === 'para') return para(deger, kr.para_birimi, dil);
  if (kr.tur === 'evet_hayir') return deger >= 1 ? t('hedefler.ortak.evet') : t('hedefler.ortak.hayir');
  if (kr.tur === 'yuzde') return `${sayiYaz(deger, dil)}%`;
  return kr.birim ? `${sayiYaz(deger, dil)} ${kr.birim}` : sayiYaz(deger, dil);
}

/** Kuruş → girdi metni ("1250,50"). */
export function kurusMetni(kurus: number | null | undefined): string {
  if (kurus === null || kurus === undefined) return '';
  const eksi = kurus < 0;
  const a = Math.round(Math.abs(kurus));
  return `${eksi ? '-' : ''}${Math.floor(a / 100)},${String(a % 100).padStart(2, '0')}`;
}

/** Değer → form girdi metni (para kuruştan). */
export function girdiMetni(tur: KrTuru, deger: number | null | undefined): string {
  if (deger === null || deger === undefined) return '';
  if (tur === 'para') return kurusMetni(deger);
  return String(deger).replace('.', ',');
}

export function gunYaz(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  const [y, a, g] = iso.slice(0, 10).split('-').map(Number);
  try {
    return new Intl.DateTimeFormat(yerelAd(dil), { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(Date.UTC(y, a - 1, g)));
  } catch {
    return iso.slice(0, 10);
  }
}

export function zamanYaz(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(yerelAd(dil), { dateStyle: 'short', timeStyle: 'short' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/** Dönemin görünen adı (adı yoksa türden). */
export function donemAdi(t: TFunction, d: Pick<Donem, 'ad' | 'tur' | 'yil' | 'ceyrek' | 'baslangic' | 'bitis'>, dil: string): string {
  if (d.ad) return d.ad;
  if (d.tur === 'ceyrek' && d.yil && d.ceyrek) return t('hedefler.donem.ceyrekAdi', { yil: d.yil, ceyrek: d.ceyrek });
  if (d.tur === 'yil' && d.yil) return t('hedefler.donem.yilAdi', { yil: d.yil });
  return `${gunYaz(d.baslangic, dil)} – ${gunYaz(d.bitis, dil)}`;
}

export const DURUM_RENGI: Record<IlerlemeDurumu, string> = {
  tamam: 'bg-emerald-400',
  yolunda: 'bg-emerald-500',
  riskli: 'bg-amber-400',
  geride: 'bg-rose-500',
};

export const DURUM_METIN_RENGI: Record<IlerlemeDurumu, string> = {
  tamam: 'text-emerald-300',
  yolunda: 'text-emerald-300',
  riskli: 'text-amber-200',
  geride: 'text-rose-300',
};

export const GUVEN_RENGI: Record<Guven, string> = {
  yolunda: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200',
  riskli: 'border-amber-400/40 bg-amber-500/10 text-amber-100',
  tehlikede: 'border-rose-400/40 bg-rose-500/10 text-rose-200',
};

export function bugun(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul' }).format(new Date());
}
