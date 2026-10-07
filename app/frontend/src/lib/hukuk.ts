import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 6H — Hukuk bürosu: panel uçları. Müşteri `/api/v1/hukukum/...` (etkin hesap `X-MK-Hesap`), yönetici
 * `/api/v1/hukuk/yonetim/...` (YALNIZ meta veri). Bu dosya yalnız sekme açıldığında (lazy) iniyor.
 */

export type HukukMod = 'yonetici' | 'musteri';
export type MuvekkilTuru = 'kisi' | 'sirket';
export type DosyaTuru = 'dava' | 'icra' | 'arabuluculuk' | 'danismanlik' | 'sozlesme' | 'diger';
export type DosyaDurumu = 'acik' | 'beklemede' | 'kapandi';
export type OlayTuru = 'durusma' | 'kesif' | 'bilirkisi' | 'kesin_sure' | 'gorev';
export type MasrafTuru = 'harc' | 'tebligat' | 'bilirkisi' | 'yol' | 'diger';
export type SureBirimi = 'gun' | 'hafta' | 'ay';
export type PortalAlani = 'konu' | 'durum' | 'durusma' | 'belgeler' | 'masraf' | 'not';

export interface Meta {
  hesap: string;
  kisi: string;
  sahip: boolean;
  dosya_siniri: number | null;
  acik_dosya_sayisi: number;
  ekip: { eposta: string; sahip: boolean }[];
  yaklasan_olay: number;
  okunmamis_mesaj: number;
  bugun: string;
  belgeler_acik: boolean;
  muvekkil_turleri: MuvekkilTuru[];
  dosya_turleri: DosyaTuru[];
  dosya_durumlari: DosyaDurumu[];
  olay_turleri: OlayTuru[];
  masraf_turleri: MasrafTuru[];
  sure_birimleri: SureBirimi[];
  para_birimleri: string[];
  portal_alanlari: Record<PortalAlani, boolean>;
  silinenler_gun: number;
  dosya_en_cok_mb: number;
}

export interface Muvekkil {
  id: number;
  tur: MuvekkilTuru;
  ad: string;
  yetkili: string;
  vergi_no: string;
  eposta: string;
  telefon: string;
  adres: string;
  notlar: string;
  kaynak: 'elle' | 'randevu';
  kaynak_id: number | null;
  portal_acik: boolean;
  portal_baglantisi: string | null;
  portal_olusturma_at: string | null;
  portal_son_at: string | null;
  silindi_at: string | null;
  dosya_sayisi?: number;
  okunmamis?: number;
  dosyalar?: Dosya[];
}

export interface KarsiTaraf {
  ad: string;
  vergi_no: string;
  vekil: string;
}

export interface SonrakiOlay {
  tur: OlayTuru;
  tarih: string;
  saat: string;
  kalan_gun: number;
}

export interface Dosya {
  id: number;
  muvekkil_id: number;
  muvekkil_ad: string | null;
  tur: DosyaTuru;
  dosya_no: string;
  esas_no: string;
  mahkeme: string;
  karsi_taraflar: KarsiTaraf[];
  konu: string;
  durum: DosyaDurumu;
  sorumlu_email: string;
  etiketler: string[];
  acilis_tarihi: string | null;
  kapanis_tarihi: string | null;
  notlar: string;
  gizli: boolean;
  portal_acik: boolean;
  portal_alanlari: Record<PortalAlani, boolean>;
  muvekkil_notu: string;
  baslik: string;
  silindi_at: string | null;
  sonraki_olay?: SonrakiOlay | null;
}

export interface Catisma {
  rol: 'muvekkil' | 'karsi_taraf';
  eslesme: 'vergi_no' | 'tam' | 'kismi';
  onem: 'catisma' | 'bilgi';
  gizli: boolean;
  ad?: string;
  muvekkil_id?: number | null;
  muvekkil_ad?: string | null;
  dosya_id?: number | null;
  dosya_baslik?: string | null;
  aranan?: string;
}

export interface Olay {
  id: number;
  dosya_id: number | null;
  dosya_baslik: string | null;
  tur: OlayTuru;
  baslik: string;
  tarih: string;
  saat: string;
  yer: string;
  notlar: string;
  sorumlu_email: string;
  tamamlandi: boolean;
  kalan_gun: number;
  hesap: SureSonucu | null;
  gizli: boolean;
}

export interface Zaman {
  id: number;
  dosya_id: number;
  tarih: string;
  sure_dk: number;
  aciklama: string;
  faturalanabilir: boolean;
  kisi_email: string;
}

export interface Masraf {
  id: number;
  dosya_id: number;
  tur: MasrafTuru;
  tutar_kurus: number;
  para_birimi: string;
  tarih: string;
  aciklama: string;
  avanstan: boolean;
  makbuz_ek_id: number | null;
}

export interface MasrafToplami {
  para_birimi: string;
  toplam_kurus: number;
  avans_kurus: number;
}

export interface Ek {
  id: number;
  dosya_id: number;
  tip: 'belge' | 'makbuz' | 'baglanti';
  ad: string;
  tur: string;
  boyut: number;
  belge_id: number | null;
  muvekkile_gorunur: boolean;
  yukleyen: string;
  created_at: string | null;
}

export interface Mesaj {
  id: number;
  muvekkil_id: number;
  muvekkil_ad?: string | null;
  dosya_id: number | null;
  yon: 'muvekkil' | 'buro';
  metin: string;
  yazan: string;
  okundu: boolean;
  created_at: string | null;
}

export interface Tatil {
  id: number;
  ad: string;
  tarih: string;
  ay_gun: string | null;
  bitis: string | null;
  tekrar: boolean;
  yarim: boolean;
  tur: 'sabit' | 'dini' | 'diger';
}

export interface Ayarlar {
  buro_adi: string;
  hatirlatma_gunleri: number[];
  sabah_saati: string;
  adli_tatil_bas: string;
  adli_tatil_bit: string;
  adli_tatil_uzatma_gun: number;
  adli_tatil_varsayilan: boolean;
}

export interface SureAdimi {
  kural: 'hmk92' | 'hmk93' | 'hmk104';
  tarih: string;
  birim?: SureBirimi;
  miktar?: number;
  atlanan?: { tarih: string; neden: 'tatil' | 'hafta_sonu'; ad: string | null }[];
  adli_tatil_bitis?: string;
  uzatma_gun?: number;
}

export interface SureSonucu {
  baslangic: string;
  miktar: number;
  birim: SureBirimi;
  adli_tatil: boolean;
  ham_son_gun: string;
  son_gun: string;
  adimlar: SureAdimi[];
  uyarilar: ('adli_tatil_icinde' | 'yarim_gun')[];
}

export interface HesapMetasi {
  hesap_email: string;
  modul_acik: boolean;
  muvekkil_sayisi: number;
  dosya_sayisi: number;
  acik_dosya: number;
  kapanan_dosya: number;
  yaklasan_sure: number;
  yaklasan_olay: number;
  depolama_bayt: number;
  ek_sayisi: number;
  portal_bagli_muvekkil: number;
}

export class HukukUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): HukukUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new HukukUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new HukukUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new HukukUcHatasi(durum, 'bulunamadi');
  return new HukukUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new HukukUcHatasi(0, 'ag');
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

function sorgu(p: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : '';
}

const M = '/api/v1/hukukum';

export function hukukApi() {
  const D = (id: number) => `${M}/dosyalar/${id}`;
  const yukle = async <T>(url: string, dosya: File, ek: Record<string, string> = {}): Promise<T> => {
    const form = new FormData();
    form.append('dosya', dosya);
    for (const [k, v] of Object.entries(ek)) form.append(k, v);
    const y = await hamIstek(url, { method: 'POST', body: form });
    return (await y.json()) as T;
  };
  const indir = async (url: string, ad: string) => blobIndir(await (await hamIstek(url, { method: 'GET' })).blob(), ad);
  return {
    meta: () => istek<Meta>('GET', `${M}/meta`),
    ayarlar: () => istek<Ayarlar>('GET', `${M}/ayarlar`),
    ayarlariKaydet: (g: Partial<Ayarlar>) => istek<Ayarlar>('PUT', `${M}/ayarlar`, g),
    tatiller: () => istek<{ items: Tatil[] }>('GET', `${M}/tatiller`),
    tatilEkle: (g: Partial<Tatil>) => istek<Tatil>('POST', `${M}/tatiller`, g),
    tatilSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${M}/tatiller/${id}`),
    sureHesapla: (g: { baslangic: string; miktar: number; birim: SureBirimi; adli_tatil: boolean }) =>
      istek<SureSonucu>('POST', `${M}/sure-hesapla`, g),
    muvekkiller: (q?: string) => istek<{ items: Muvekkil[] }>('GET', `${M}/muvekkiller${sorgu({ q })}`),
    muvekkil: (id: number) => istek<Muvekkil>('GET', `${M}/muvekkiller/${id}`),
    muvekkilEkle: (g: Partial<Muvekkil>) => istek<{ muvekkil: Muvekkil; catisma: Catisma[] }>('POST', `${M}/muvekkiller`, g),
    muvekkilKaydet: (id: number, g: Partial<Muvekkil>) =>
      istek<{ muvekkil: Muvekkil; catisma: Catisma[] }>('PUT', `${M}/muvekkiller/${id}`, g),
    muvekkilSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${M}/muvekkiller/${id}`),
    muvekkilGeriAl: (id: number) => istek<Muvekkil>('POST', `${M}/muvekkiller/${id}/geri-al`),
    portalOlustur: (id: number) => istek<{ baglanti: string; muvekkil: Muvekkil }>('POST', `${M}/muvekkiller/${id}/portal`),
    portalIptal: (id: number) => istek<{ ok: boolean }>('DELETE', `${M}/muvekkiller/${id}/portal`),
    randevuKayitlari: () =>
      istek<{ items: { id: number; ad: string; eposta: string; telefon: string; baslangic: string | null }[] }>('GET', `${M}/randevu-kayitlari`),
    catisma: (g: { ad?: string; vergi_no?: string; rol: 'muvekkil' | 'karsi_taraf'; haric_muvekkil_id?: number; haric_dosya_id?: number }) =>
      istek<{ items: Catisma[] }>('POST', `${M}/catisma`, g),
    dosyalar: (p: { durum?: string; muvekkil_id?: number; q?: string; sorumlu?: string } = {}) =>
      istek<{ items: Dosya[] }>('GET', `${M}/dosyalar${sorgu(p)}`),
    dosya: (id: number) => istek<Dosya>('GET', D(id)),
    dosyaEkle: (g: Partial<Dosya>) => istek<{ dosya: Dosya; catisma: Catisma[] }>('POST', `${M}/dosyalar`, g),
    dosyaKaydet: (id: number, g: Partial<Dosya>) => istek<{ dosya: Dosya; catisma: Catisma[] }>('PUT', D(id), g),
    dosyaSil: (id: number) => istek<{ ok: boolean }>('DELETE', D(id)),
    dosyaGeriAl: (id: number) => istek<Dosya>('POST', `${D(id)}/geri-al`),
    silinenler: () => istek<{ muvekkiller: Muvekkil[]; dosyalar: Dosya[]; gun: number }>('GET', `${M}/silinenler`),
    zaman: (id: number) => istek<{ items: Zaman[]; toplam_dk: number; faturalanabilir_dk: number }>('GET', `${D(id)}/zaman`),
    zamanEkle: (id: number, g: Partial<Zaman>) => istek<Zaman>('POST', `${D(id)}/zaman`, g),
    zamanSil: (id: number, zid: number) => istek<{ ok: boolean }>('DELETE', `${D(id)}/zaman/${zid}`),
    masraflar: (id: number) => istek<{ items: Masraf[]; toplamlar: MasrafToplami[] }>('GET', `${D(id)}/masraflar`),
    masrafEkle: (id: number, g: Record<string, unknown>) => istek<Masraf>('POST', `${D(id)}/masraflar`, g),
    masrafSil: (id: number, mid: number) => istek<{ ok: boolean }>('DELETE', `${D(id)}/masraflar/${mid}`),
    makbuzYukle: (id: number, mid: number, dosya: File) => yukle<{ masraf: Masraf; ek: Ek }>(`${D(id)}/masraflar/${mid}/makbuz`, dosya),
    ekler: (id: number) => istek<{ items: Ek[]; toplam_bayt: number }>('GET', `${D(id)}/ekler`),
    ekYukle: (id: number, dosya: File, gorunur: boolean) => yukle<Ek>(`${D(id)}/ekler`, dosya, { muvekkile_gorunur: String(gorunur) }),
    ekBaglanti: (id: number, belge_id: number) => istek<Ek>('POST', `${D(id)}/ekler/baglanti`, { belge_id }),
    ekKaydet: (id: number, eid: number, g: Partial<Ek>) => istek<Ek>('PUT', `${D(id)}/ekler/${eid}`, g),
    ekSil: (id: number, eid: number) => istek<{ ok: boolean }>('DELETE', `${D(id)}/ekler/${eid}`),
    ekIndir: (id: number, e: Ek) => indir(`${D(id)}/ekler/${e.id}/indir`, e.ad),
    belgelerim: () => istek<{ items: { id: number; baslik: string; tur: string }[]; modul_acik: boolean }>('GET', `${M}/belgelerim`),
    dokumIndir: (id: number, dil: string, ad: string) => indir(`${D(id)}/dokum.pdf${sorgu({ dil })}`, ad),
    olaylar: (p: { bas?: string; bit?: string; sorumlu?: string; dosya_id?: number; tamamlanan?: boolean } = {}) =>
      istek<{ items: Olay[]; bugun: string }>('GET', `${M}/olaylar${sorgu(p)}`),
    olayEkle: (g: Record<string, unknown>) => istek<Olay>('POST', `${M}/olaylar`, g),
    olayKaydet: (id: number, g: Record<string, unknown>) => istek<Olay>('PUT', `${M}/olaylar/${id}`, g),
    olaySil: (id: number) => istek<{ ok: boolean }>('DELETE', `${M}/olaylar/${id}`),
    icsIndir: (sorumlu: string, dil: string) =>
      indir(`${M}/takvim.ics${sorgu({ sorumlu, dil })}`, `hukuk-takvim${sorumlu ? `-${sorumlu.split('@')[0]}` : ''}.ics`),
    mesajlar: (muvekkil_id?: number) => istek<{ items: Mesaj[] }>('GET', `${M}/mesajlar${sorgu({ muvekkil_id })}`),
    mesajYaz: (g: { muvekkil_id: number; metin: string; dosya_id?: number }) => istek<Mesaj>('POST', `${M}/mesajlar`, g),
    okundu: (muvekkil_id: number) => istek<{ ok: boolean }>('POST', `${M}/mesajlar/okundu`, { muvekkil_id }),
  };
}

export type HukukApi = ReturnType<typeof hukukApi>;

export const hukukYonetimApi = {
  ozet: () => istek<{ hesaplar: HesapMetasi[]; toplam: Record<string, number>; gizlilik: string }>('GET', '/api/v1/hukuk/yonetim/ozet'),
};

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof HukukUcHatasi) {
    return t(`hukuk.hata.${e.kod}`, { ...e.ek, defaultValue: t('hukuk.hata.genel') }) as string;
  }
  return t('hukuk.hata.genel');
}

export function paraYaz(kurus: number, para: string, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: para || 'TRY' }).format((kurus || 0) / 100);
  } catch {
    return `${((kurus || 0) / 100).toFixed(2)} ${para}`;
  }
}

export function gunYaz(gun: string | null | undefined, dil: string, secenek: Intl.DateTimeFormatOptions = { dateStyle: 'medium' }): string {
  if (!gun) return '';
  try {
    return new Intl.DateTimeFormat(dil, { ...secenek, timeZone: 'UTC' }).format(new Date(`${gun.slice(0, 10)}T00:00:00Z`));
  } catch {
    return gun;
  }
}

export function boyutYaz(bayt: number): string {
  if (bayt >= 1024 * 1024) return `${(bayt / 1024 / 1024).toFixed(1)} MB`;
  if (bayt >= 1024) return `${Math.round(bayt / 1024)} KB`;
  return `${bayt} B`;
}

/** "YYYY-MM-DD" + n gün (UTC; saat dilimi kayması yok). */
export function gunEkle(gun: string, n: number): string {
  const d = new Date(`${gun}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function haftaBasi(gun: string): string {
  const d = new Date(`${gun}T00:00:00Z`);
  const gunNo = (d.getUTCDay() + 6) % 7; // pazartesi = 0
  return gunEkle(gun, -gunNo);
}

export function ayBasi(gun: string): string {
  return `${gun.slice(0, 7)}-01`;
}

export function ayEkle(gun: string, n: number): string {
  const d = new Date(`${gun.slice(0, 7)}-01T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + n);
  return d.toISOString().slice(0, 10);
}
