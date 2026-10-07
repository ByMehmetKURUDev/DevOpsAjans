import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 6I — İnsan kaynakları: panel uçları ve küçük yardımcılar.
 *
 * Müşteri paneli `/api/v1/ik/...` (etkin hesap `X-MK-Hesap`), ajans paneli `/api/v1/ik-yonetim/...`:
 * `hesap` verilmezse ajansın KENDİ personeli (tam yönetim), verilirse müşteri hesabının SALT OKUNUR destek
 * görünümü. Bu dosya yalnız sekme açıldığında (lazy) iniyor.
 */

export type IkMod = 'musteri' | 'yonetici';
export type IzinTuru = 'yillik' | 'mazeret' | 'ucretsiz' | 'rapor' | 'dogum' | 'babalik' | 'evlilik' | 'olum' | 'diger';
export type IzinDurumu = 'beklemede' | 'onaylandi' | 'reddedildi' | 'iptal';
export type YasGrubu = 'genel' | 'genc' | 'ileri';

export const IZIN_TURLERI: IzinTuru[] = ['yillik', 'mazeret', 'ucretsiz', 'rapor', 'dogum', 'babalik', 'evlilik', 'olum', 'diger'];
export const YASAL_TURLER: IzinTuru[] = ['dogum', 'babalik', 'evlilik', 'olum'];

export interface KidemKurali {
  yil: number;
  gun: number;
}

export interface Ayarlar {
  kapsam: string;
  firma_adi: string;
  calisma_gunleri: number[];
  kidem_kurallari: KidemKurali[];
  yas_en_az_gun: number;
  yasal_gunler: Record<string, number>;
  kapali_sabitler: string[];
  uyari_izinli: boolean;
  uyari_cakisma: boolean;
  uyari_dinlenme: boolean;
  en_az_dinlenme_saat: number;
  uyari_haftalik: boolean;
  haftalik_en_cok_saat: number;
  varsayilan: {
    calisma_gunleri: number[];
    kidem_kurallari: KidemKurali[];
    yas_en_az_gun: number;
    yasal_gunler: Record<string, number>;
    en_az_dinlenme_saat: number;
    haftalik_en_cok_saat: number;
  };
}

export interface Meta {
  yonetici: boolean;
  hesap: string | null;
  ajans: boolean;
  salt_okunur: boolean;
  kisi: string;
  personel_siniri: number | null;
  aktif_personel: number;
  bekleyen_izin: number;
  departmanlar: string[];
  bugun: string;
  en_cok_csv: number;
  ayarlar: Ayarlar;
  portal_tabani: string;
}

export interface Bakiye {
  devir: number;
  devir_tarihi: string;
  kazanilan: number;
  kullanilan: number;
  bekleyen: number;
  kalan: number;
  kullanilabilir: number;
  kidem_yil: number;
  yillik_hak: number;
  sonraki: { tarih: string; yil: number; gun: number } | null;
  hakedisler: { tarih: string; yil: number; gun: number }[];
}

export interface Personel {
  id: number;
  hesap_email: string | null;
  ad: string;
  gorev: string;
  departman: string;
  durum: 'aktif' | 'ayrildi';
  ise_giris: string;
  ayrilis_tarihi: string | null;
  eposta?: string;
  telefon?: string;
  yas_grubu?: YasGrubu;
  devir_gun?: number;
  devir_tarihi?: string | null;
  yillik_gun_ozel?: number | null;
  notlar?: string;
  dil?: string;
  portal_acik?: boolean;
  portal_son_at?: string | null;
  bakiye?: Bakiye;
  bekleyen_izin?: number;
}

export interface Izin {
  id: number;
  personel_id: number;
  personel_ad: string | null;
  tur: IzinTuru;
  baslangic: string;
  bitis: string;
  yarim_gun: boolean;
  gun: number;
  takvim_gunu: number;
  durum: IzinDurumu;
  aciklama: string;
  karar_notu: string;
  karar_veren: string | null;
  karar_at: string | null;
  kaynak: 'panel' | 'portal';
  talep_eden: string | null;
  iptal_eden: string | null;
  iptal_at: string | null;
  created_at: string | null;
}

export interface Uyari {
  tur: string;
  [k: string]: unknown;
}

export interface PersonelAyrinti extends Personel {
  izinler: Izin[];
  dosyalar: { id: number; ad: string; tur: string; boyut: number; created_at: string | null }[];
}

export interface Sablon {
  id: number;
  ad: string;
  baslangic: string;
  bitis: string;
  mola_dk: number;
  renk: string;
  aktif: boolean;
  sira: number;
  gece: boolean;
  net_dk: number;
}

export interface Vardiya {
  id: number;
  personel_id: number;
  tarih: string;
  bas: string;
  bit: string;
  baslangic: string;
  bitis: string;
  mola_dk: number;
  net_dk: number;
  sablon_id: number | null;
  durum: 'taslak' | 'yayinda';
  degisti: boolean;
  notlar: string;
}

export interface HaftaPlani {
  hafta_bas: string;
  gunler: string[];
  personel: Personel[];
  vardiyalar: Vardiya[];
  izinli: Record<string, Record<string, IzinTuru>>;
  bekleyen_izin: Record<string, string[]>;
  tatiller: Record<string, number>;
  uyarilar: Uyari[];
  toplam_dk: Record<string, number>;
  sayilar: { taslak: number; yayinda: number; degisti: number };
  sinirlar: { haftalik_en_cok_saat: number; en_az_dinlenme_saat: number };
}

export interface Takvim {
  ay: string;
  ilk: string;
  son: string;
  calisma_gunleri: number[];
  izinler: Izin[];
  tatiller: { tarih: string; ad: string; oran: number }[];
}

export interface Tatiller {
  yil: number;
  sabit: { tarih: string; anahtar: string; sabit: string; ad: string; yarim: boolean; kapali: boolean }[];
  eklenen: { id: number; tarih: string; ad: string; yarim: boolean }[];
}

export interface HesapOzeti {
  hesap_email: string;
  firma_adi: string | null;
  personel: number;
  bekleyen_izin: number;
}

// ---------------------------------------------------------------------------
// Hata
// ---------------------------------------------------------------------------
export class IkHatasi extends Error {
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

function hataCoz(durum: number, detay: unknown): IkHatasi {
  if (detay && typeof detay === 'object' && 'kod' in (detay as Record<string, unknown>)) {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new IkHatasi(durum, String(kod), ek);
  }
  if (durum === 429) return new IkHatasi(durum, 'cok_hizli');
  if (durum === 404) return new IkHatasi(durum, 'bulunamadi');
  if (durum === 403) return new IkHatasi(durum, 'yetki_yok');
  return new IkHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new IkHatasi(0, 'ag');
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

export function ikApi(mod: IkMod, hesap?: string) {
  const T = mod === 'yonetici' ? '/api/v1/ik-yonetim' : '/api/v1/ik';
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
    hesaplar: () => istek<{ items: HesapOzeti[] }>('GET', '/api/v1/ik-yonetim/hesaplar'),
    meta: () => istek<Meta>('GET', u('/meta')),
    ayarlarKaydet: (g: Partial<Ayarlar> | Record<string, unknown>) => istek<Ayarlar>('PUT', u('/ayarlar'), g),
    gunHesapla: (bas: string, bit: string, yarim = false) => istek<{ gun: number; takvim_gunu: number }>('GET', u('/gun-hesapla', { bas, bit, yarim })),
    tatiller: (yil: number) => istek<Tatiller>('GET', u('/tatiller', { yil })),
    tatilEkle: (g: { tarih: string; bitis?: string; ad: string; yarim?: boolean }) => istek<{ eklenen: unknown[] }>('POST', u('/tatiller'), g),
    tatilSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/tatiller/${id}`)),
    personelListesi: (q: { durum?: string; ara?: string; departman?: string } = {}) =>
      istek<{ items: Personel[]; toplam: number }>('GET', u('/personel', q)),
    personel: (id: number) => istek<PersonelAyrinti>('GET', u(`/personel/${id}`)),
    personelEkle: (g: Record<string, unknown>) => istek<Personel>('POST', u('/personel'), g),
    personelGuncelle: (id: number, g: Record<string, unknown>) => istek<Personel>('PUT', u(`/personel/${id}`), g),
    personelSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/personel/${id}`)),
    baglanti: (id: number, islem: 'goster' | 'yenile' | 'iptal', gonder = false) =>
      istek<{ portal_acik: boolean; adres: string | null; gonderildi?: boolean }>('POST', u(`/personel/${id}/baglanti`), { islem, gonder }),
    personelCsv: () => indir('/personel.csv', {}, 'personel.csv'),
    iceAktar: (csv: string) =>
      istek<{ eklenen: number; guncellenen: number; hata_sayisi: number; hatalar: { satir: number; kod: string; alan?: string }[] }>(
        'POST',
        u('/personel/ice-aktar'),
        { csv }
      ),
    async dosyaEkle(id: number, dosya: File): Promise<{ id: number; ad: string }> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(u(`/personel/${id}/dosyalar`), { method: 'POST', body: form });
      return y.json();
    },
    dosyaIndir: (id: number, ad: string) => indir(`/dosyalar/${id}`, {}, ad),
    dosyaSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/dosyalar/${id}`)),
    izinler: (q: { durum?: string; personel_id?: number; tur?: string; bas?: string; bit?: string } = {}) =>
      istek<{ items: Izin[]; toplam: number }>('GET', u('/izinler', q)),
    izin: (id: number) =>
      istek<{ izin: Izin; personel: Personel; uyarilar: Uyari[]; ayni_tarihte: { personel_id: number; ad: string; baslangic: string; bitis: string }[] }>(
        'GET',
        u(`/izinler/${id}`)
      ),
    izinEkle: (g: Record<string, unknown>) => istek<{ izin: Izin; uyarilar: Uyari[] }>('POST', u('/izinler'), g),
    karar: (id: number, karar: 'onay' | 'ret', not?: string) => istek<{ izin: Izin }>('POST', u(`/izinler/${id}/karar`), { karar, not }),
    iptal: (id: number) => istek<{ izin: Izin }>('POST', u(`/izinler/${id}/iptal`), {}),
    geriAl: (id: number) => istek<{ izin: Izin }>('POST', u(`/izinler/${id}/geri-al`), {}),
    takvim: (ay: string) => istek<Takvim>('GET', u('/izinler/takvim', { ay })),
    izinIcs: () => indir('/izinler.ics', {}, 'izin-takvimi.ics'),
    izinCsv: () => indir('/izinler.csv', {}, 'izinler.csv'),
    sablonlar: () => istek<{ items: Sablon[] }>('GET', u('/sablonlar')),
    sablonEkle: (g: Partial<Sablon>) => istek<Sablon>('POST', u('/sablonlar'), g),
    sablonGuncelle: (id: number, g: Partial<Sablon>) => istek<Sablon>('PUT', u(`/sablonlar/${id}`), g),
    sablonSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/sablonlar/${id}`)),
    hafta: (hafta: string) => istek<HaftaPlani>('GET', u('/vardiyalar', { hafta })),
    vardiyaEkle: (g: Record<string, unknown>) => istek<{ vardiya: Vardiya; uyarilar: Uyari[] }>('POST', u('/vardiyalar'), g),
    vardiyaGuncelle: (id: number, g: Record<string, unknown>) => istek<{ vardiya: Vardiya; uyarilar: Uyari[] }>('PUT', u(`/vardiyalar/${id}`), g),
    vardiyaSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/vardiyalar/${id}`)),
    kopyala: (hafta: string, uzerine_yaz = false) =>
      istek<{ eklenen: number; atlanan: number; kaynak_hafta: string }>('POST', u('/vardiyalar/kopyala'), { hafta, uzerine_yaz }),
    yayinla: (hafta: string, bildir = true) =>
      istek<{ yayinlanan: number; etkilenen: number; bildirilen: number }>('POST', u('/vardiyalar/yayinla'), { hafta, bildir }),
    planCsv: (hafta: string) => indir('/vardiyalar.csv', { hafta }, `vardiya-${hafta}.csv`),
    planPdf: (hafta: string, dil: string) => indir('/vardiyalar.pdf', { hafta, dil }, `vardiya-${hafta}.pdf`),
  };
}

export type IkApi = ReturnType<typeof ikApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof IkHatasi) {
    return t(`ik.hata.${e.kod}`, { ...e.ek, defaultValue: t('ik.hata.genel') }) as string;
  }
  return t('ik.hata.genel');
}

// ---------------------------------------------------------------------------
// Tarih ve biçim
// ---------------------------------------------------------------------------
function yerelAd(dil: string): string {
  return dil === 'ar' ? 'ar-u-nu-latn' : dil;
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

export function aralikYaz(bas: string, bit: string, dil: string): string {
  return bas === bit ? gunYaz(bas, dil) : `${gunYaz(bas, dil)} – ${gunYaz(bit, dil)}`;
}

export function sayiYaz(n: number | null | undefined, dil: string): string {
  if (n === null || n === undefined) return '—';
  try {
    return new Intl.NumberFormat(yerelAd(dil), { maximumFractionDigits: 1 }).format(n);
  } catch {
    return String(n);
  }
}

/** ISO gün + n gün. */
export function gunEkle(iso: string, n: number): string {
  const [y, a, g] = iso.slice(0, 10).split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1, g + n));
  return d.toISOString().slice(0, 10);
}

/** Pazartesi başlangıçlı hafta. */
export function haftaBasi(iso: string): string {
  const [y, a, g] = iso.slice(0, 10).split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1, g));
  const gun = (d.getUTCDay() + 6) % 7;
  return gunEkle(iso, -gun);
}

/** 0 = Pazartesi … 6 = Pazar. */
export function haftaGunu(iso: string): number {
  const [y, a, g] = iso.slice(0, 10).split('-').map(Number);
  return (new Date(Date.UTC(y, a - 1, g)).getUTCDay() + 6) % 7;
}

/** Haftanın günlerinin kısa adları (Pazartesi başlangıçlı), seçili dilde. */
export function gunAdlari(dil: string, bicim: 'short' | 'narrow' | 'long' = 'short'): string[] {
  const sonuc: string[] = [];
  for (let i = 0; i < 7; i++) {
    try {
      sonuc.push(new Intl.DateTimeFormat(yerelAd(dil), { weekday: bicim, timeZone: 'UTC' }).format(new Date(Date.UTC(2026, 0, 5 + i))));
    } catch {
      sonuc.push(String(i + 1));
    }
  }
  return sonuc;
}

export function saatYaz(dk: number, dil: string): string {
  return sayiYaz(Math.round((dk / 60) * 10) / 10, dil);
}

export const DURUM_RENGI: Record<IzinDurumu, string> = {
  beklemede: 'border-amber-400/40 bg-amber-500/15 text-amber-200',
  onaylandi: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  reddedildi: 'border-rose-400/40 bg-rose-500/15 text-rose-200',
  iptal: 'border-zinc-400/30 bg-zinc-500/10 text-zinc-300',
};

export const TUR_RENGI: Record<IzinTuru, string> = {
  yillik: '#7c3aed',
  mazeret: '#0ea5e9',
  ucretsiz: '#64748b',
  rapor: '#f43f5e',
  dogum: '#ec4899',
  babalik: '#14b8a6',
  evlilik: '#f59e0b',
  olum: '#6b7280',
  diger: '#22c55e',
};

/** Ortak girdi sınıfında `w-full` yerine dar genişlik (ikisi birlikte olursa `w-full` kazanıyordu). */
export const dar = (sinif: string, genislik: string) => sinif.replace('w-full', genislik);
