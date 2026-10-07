import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 5B — belgeler, wiki ve strateji araçları: uçlar ve tipler.
 *
 * Yönetici `/api/v1/belgeler/...`, müşteri `/api/v1/belgelerim/...` (etkin hesap `X-MK-Hesap`
 * başlığıyla). İki panel aynı bileşenleri kullanıyor. Markdown → HTML ve temizleme YALNIZ
 * sunucuda (`/onizle` ve ayrıntı yanıtındaki `html`): ön yüz Markdown'ı kendisi çevirmiyor.
 * Strateji şablonlarının kutuları ve ızgara düzeni sunucudan (`/meta`) — kodda tek yer.
 */

export type BelgeMod = 'yonetici' | 'musteri';
export type Kategori = 'belge' | 'strateji';
export type Alan = 'ajans' | 'musteri' | 'proje';
export type Gorunurluk = 'ekip' | 'paylasilan';
export type AiIslem = 'yaz' | 'ozetle' | 'duzelt' | 'taslak';

export interface Kutu {
  anahtar: string;
  sutun: number;
  satir: number;
  en: number;
  boy: number;
}

export interface StratejiSablonu {
  tur: string;
  sutun: number;
  satir: number;
  yatay: boolean;
  kutular: Kutu[];
}

export interface Kullanim {
  ay: number;
  ay_kredi: number;
  bugun: number;
  sinirlar: { aylik_uretim: number | null; gunluk_uretim: number | null; kredi_ile_asim: boolean };
  ajans: boolean;
}

export interface Meta {
  turler: string[];
  strateji_sablonlari: StratejiSablonu[];
  alanlar: Alan[];
  gorunurlukler: Gorunurluk[];
  sinirlar: Record<string, number>;
  surum_siniri: number;
  ai_hazir: boolean;
  ai_islemleri: AiIslem[];
  kullanim?: Kullanim;
  modul_acik?: boolean;
  kendi_belge?: boolean;
  belge_siniri?: number;
  belge_sayisi?: number;
}

export interface Yapilacak {
  satir: number;
  metin: string;
  tamam: boolean;
  atananlar: string[];
  gorev_id: number | null;
}

export interface Belge {
  id: number;
  tur: string;
  strateji: boolean;
  baslik: string;
  etiketler: string[];
  alan: Alan;
  musteri_email: string | null;
  proje_id: number | null;
  proje_adi: string | null;
  gorunurluk: Gorunurluk;
  musteri_belgesi: boolean;
  sahip_hesap: string | null;
  sabit: boolean;
  surum: number;
  olusturan: string | null;
  son_duzenleyen: string | null;
  son_duzenleyen_rol: 'admin' | 'client' | null;
  paylasildi_at: string | null;
  okundu_at: string | null;
  okuyan: string | null;
  okundu_surum: number | null;
  created_at: string | null;
  updated_at: string | null;
  ozet: string;
  acik_yapilacak: number;
}

export interface StratejiIcerigi {
  isletme: string;
  kutular: Record<string, string>;
}

export interface BelgeAyrintisi extends Belge {
  icerik?: string;
  html?: string;
  yapilacaklar?: Yapilacak[];
  strateji_icerik?: StratejiIcerigi;
}

export interface Liste {
  items: Belge[];
  etiketler: { ad: string; sayi: number }[];
  kendi_belge?: boolean;
}

export interface Ozet {
  paylasilan: number;
  paylasilan_belge: number;
  paylasilan_strateji: number;
  modul_acik: boolean;
  izin: boolean;
}

export interface Surum {
  id: number;
  belge_id: number;
  surum: number;
  baslik: string;
  duzenleyen: string | null;
  rol: string | null;
  aciklama: string | null;
  created_at: string | null;
  boyut: number;
  icerik?: string;
  html?: string;
  strateji_icerik?: StratejiIcerigi;
}

export interface YapilacakOgesi extends Yapilacak {
  belge_id: number;
  belge_baslik: string;
  proje_id: number | null;
  musteri_email: string | null;
  bana: boolean;
  updated_at: string | null;
  salt_okunur?: boolean;
}

export interface Uyari {
  tur: string;
  eslesen: string[];
}

export interface AiSonucu {
  islem: AiIslem;
  sahte: boolean;
  kredi: number;
  metin?: string;
  kutular?: Record<string, string>;
  uyarilar: Uyari[] | Record<string, Uyari[]>;
  kullanim: Kullanim;
}

export interface Suzgec {
  q?: string;
  etiket?: string;
  tur?: string;
  alan?: string;
  kaynak?: string;
}

export interface BelgeGovdesi {
  tur?: string;
  baslik?: string;
  icerik?: string | StratejiIcerigi;
  etiketler?: string[];
  alan?: Alan;
  musteri_email?: string | null;
  proje_id?: number | null;
  gorunurluk?: Gorunurluk;
  sabit?: boolean;
  surum?: number;
}

export class BelgeHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): BelgeHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new BelgeHatasi(durum, kod, ek);
  }
  if (durum === 429) return new BelgeHatasi(durum, 'cok_hizli');
  if (durum === 404) return new BelgeHatasi(durum, 'bulunamadi');
  if (durum === 403) return new BelgeHatasi(durum, 'yetki');
  return new BelgeHatasi(durum, durum === 0 ? 'ag' : 'genel');
}

function govdeyiAc<T>(yanit: unknown): T {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T;
}

async function istek<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    return govdeyiAc<T>(await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> | undefined }));
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

async function dosyaIndir(url: string, ad: string): Promise<void> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, { headers: oturumBasliklari() });
  } catch {
    throw new BelgeHatasi(0, 'ag');
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

function sorgu(o: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
}

/** Dosya adı: başlıktan ASCII, sonuna kimlik (sunucunun adıyla aynı biçim). */
export function dosyaAdi(b: { id: number; baslik: string }, uzanti: string): string {
  const temel = b.baslik
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ı/g, 'i')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  return `${temel || 'belge'}-${b.id}.${uzanti}`;
}

export function belgeApi(mod: BelgeMod) {
  const T = mod === 'yonetici' ? '/api/v1/belgeler' : '/api/v1/belgelerim';
  return {
    mod,
    meta: () => istek<Meta>('GET', `${T}/meta`),
    liste: (s: Suzgec = {}) => istek<Liste>('GET', `${T}${sorgu({ ...s })}`),
    getir: (id: number) => istek<BelgeAyrintisi>('GET', `${T}/${id}`),
    olustur: (g: BelgeGovdesi) => istek<BelgeAyrintisi>('POST', T, g),
    guncelle: (id: number, g: BelgeGovdesi) => istek<BelgeAyrintisi>('PUT', `${T}/${id}`, g),
    sil: (id: number) => istek<{ silindi: number }>('DELETE', `${T}/${id}`),
    onizle: (icerik: string) => istek<{ html: string; yapilacaklar: Yapilacak[] }>('POST', `${T}/onizle`, { icerik }),
    surumler: (id: number) => istek<{ items: Surum[]; guncel: number }>('GET', `${T}/${id}/surumler`),
    surum: (id: number, sid: number) => istek<Surum>('GET', `${T}/${id}/surumler/${sid}`),
    geriYukle: (id: number, sid: number) => istek<BelgeAyrintisi>('POST', `${T}/${id}/surumler/${sid}/geri-yukle`),
    yapilacak: (id: number, g: { satir: number; metin: string; tamam: boolean }) =>
      istek<BelgeAyrintisi>('POST', `${T}/${id}/yapilacak`, g),
    gorevBagla: (id: number, g: { satir: number; metin: string; gorev_id: number }) =>
      istek<BelgeAyrintisi>('POST', `${T}/${id}/yapilacak/gorev`, g),
    yapilacaklar: (kapsam: 'bana' | 'hepsi') =>
      istek<{ items: YapilacakOgesi[]; ben: string }>('GET', `${T}/yapilacaklar${sorgu({ kapsam })}`),
    ai: (g: { islem: AiIslem; metin?: string; talimat?: string; tur?: string; isletme?: string; dil?: string }) =>
      istek<AiSonucu>('POST', `${T}/ai`, g),
    okundu: (id: number) => istek<BelgeAyrintisi>('POST', `${T}/${id}/okundu`),
    pdfIndir: (b: { id: number; baslik: string }, dil: string) => dosyaIndir(`${T}/${b.id}/pdf${sorgu({ dil })}`, dosyaAdi(b, 'pdf')),
    mdIndir: (b: { id: number; baslik: string }, dil: string) => dosyaIndir(`${T}/${b.id}/md${sorgu({ dil })}`, dosyaAdi(b, 'md')),
  };
}
export type BelgeApi = ReturnType<typeof belgeApi>;

/** Müşteri panelinin "Dosyalar ve belgeler" sekmesi için tek küçük istek. */
export function musteriOzeti(): Promise<Ozet> {
  return istek<Ozet>('GET', '/api/v1/belgelerim/ozet');
}

/** Faz 2B görev ucu: yapılacak maddesinden proje görevi (yönetici). */
export function projeGoreviOlustur(projeId: number, baslik: string, aciklama: string): Promise<{ id: number }> {
  return istek<{ id: number }>('POST', `/api/v1/gorevler/proje/${projeId}`, { baslik: baslik.slice(0, 200), aciklama });
}

export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof BelgeHatasi) {
    return t(`belgeler.hata.${e.kod}`, { ...e.ek, defaultValue: t('belgeler.hata.genel') }) as string;
  }
  return t('belgeler.hata.genel');
}

export function tarihYaz(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}
