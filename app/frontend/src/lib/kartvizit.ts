import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 4K — Dijital kartvizit + bio link ve Google yorum sayfası uçları.
 *
 * Panel: yönetici `/api/v1/kartvizit/yonetim`, `/api/v1/yorum-sayfalari/yonetim`;
 * müşteri `/api/v1/kartvizitlerim`, `/api/v1/yorum-sayfalarim` (etkin hesap
 * `X-MK-Hesap`). İki panel aynı bileşeni kullanıyor; yalnız taban yol değişiyor.
 *
 * Herkese açık sayfalar (`/kart/<slug>`, `/yorum/<slug>`) oturumsuz düz `fetch`
 * kullanıyor (`acik*` fonksiyonları) — bu dosyanın panel kısmı o sayfaların
 * paketine girmesin diye herkese açık tipler/yardımcılar `kartvizitAcik.ts`'te.
 */

export type PanelMod = 'yonetici' | 'musteri';
export type Duzen = 'kartvizit' | 'bio_link';

export interface Tema {
  sablon: string;
  renk: string;
  yazi_tipi: string;
  kose: string;
}
export interface Telefon {
  etiket: string;
  numara: string;
  tip: string;
}
export interface Web {
  etiket: string;
  url: string;
}
export interface Sosyal {
  platform: string;
  url: string;
}
export interface Baglanti {
  id?: string;
  baslik: string;
  url: string;
  simge: string;
}
export interface Hizmet {
  baslik: string;
  aciklama: string;
}
export interface Gun {
  gun: string;
  acik: boolean;
  acilis: string;
  kapanis: string;
}
export interface Saatler {
  goster: boolean;
  gunler: Gun[];
  not: string;
}
export interface Icerik {
  ad_soyad: string;
  unvan: string;
  sirket: string;
  tanitim: string;
  telefonlar: Telefon[];
  eposta: string;
  webler: Web[];
  adres: string;
  harita_url: string;
  whatsapp: string;
  sosyal: Sosyal[];
  baglantilar: Baglanti[];
  hizmetler: Hizmet[];
  calisma_saatleri: Saatler;
}
export interface Gorsel {
  id: number;
  tur: string;
  url: string;
  genislik: number;
  yukseklik: number;
  boyut?: number;
  sira?: number;
}

export interface KartKaydi {
  id: number;
  kod: string;
  slug: string;
  duzen: Duzen;
  dil: string;
  ad_soyad: string;
  unvan: string | null;
  sirket: string | null;
  icerik: Icerik;
  tema: Tema;
  foto: Gorsel | null;
  logo: Gorsel | null;
  kapak: Gorsel | null;
  galeri: Gorsel[];
  aktif: boolean;
  form_acik: boolean;
  index_acik: boolean;
  sifreli: boolean;
  hesap_email: string | null;
  olusturan_email: string | null;
  kart_adresi: string;
  qr_adresi: string;
  son30: Record<string, number>;
  okunmamis?: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface KartMeta {
  duzenler: Duzen[];
  sablonlar: string[];
  sablon_renkleri: Record<string, string>;
  yazi_tipleri: string[];
  koseler: string[];
  platformlar: string[];
  simgeler: string[];
  gunler: string[];
  telefon_tipleri: string[];
  diller: string[];
  en_cok: Record<string, number>;
  sinirlar: Record<string, number>;
  gorsel_en_cok_mb: number;
  kart_tabani: string;
  eski_slug_gun: number;
  kart_siniri: number | null;
  kart_sayisi: number | null;
  yonetici: boolean;
}

export interface YorumSayfasi {
  id: number;
  kod: string;
  slug: string;
  isletme_adi: string;
  place_id: string;
  google_adresi: string;
  tesekkur: string;
  geri_bildirim_acik: boolean;
  dil: string;
  renk: string | null;
  logo: Gorsel | null;
  aktif: boolean;
  hesap_email: string | null;
  olusturan_email: string | null;
  sayfa_adresi: string;
  qr_adresi: string;
  son30: Record<string, number>;
  okunmamis?: number;
  created_at: string | null;
}

export interface YorumMeta {
  diller: string[];
  sinirlar: Record<string, number>;
  gorsel_en_cok_mb: number;
  sayfa_tabani: string;
  eski_slug_gun: number;
  sayfa_siniri: number | null;
  sayfa_sayisi: number | null;
  yonetici: boolean;
}

export interface Mesaj {
  id: number;
  sahip_tur: 'kart' | 'yorum';
  sahip_id: number;
  sahip_baslik: string | null;
  ad: string | null;
  eposta: string | null;
  telefon: string | null;
  mesaj: string | null;
  dil: string | null;
  okundu: boolean;
  crm_aday_id: number | null;
  hesap_email: string | null;
  created_at: string | null;
}

export interface Analiz {
  toplam: Record<string, number>;
  tekil: number;
  qr: number;
  bot: number;
  donem: Record<string, number>;
  gunluk: ({ gun: string; tekil: number } & Record<string, number | string>)[];
  hedefler: { hedef: string; sayi: number; etiket?: string | null }[];
  cihazlar: { anahtar: string; sayi: number }[];
}

export interface SlugDurumu {
  uygun: boolean;
  kod?: string;
  slug?: string;
  oneri: string;
}

/** Sunucu hatası: `kod` yedi dilde metne çevriliyor (`kartvizit.hata.<kod>`). */
export class KartUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): KartUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new KartUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new KartUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new KartUcHatasi(durum, 'bulunamadi');
  if (durum === 413) return new KartUcHatasi(durum, 'gorsel_buyuk');
  return new KartUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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

/** Oturumlu ham istek (çok parçalı yükleme / dosya indirme). */
async function hamIstek(url: string, init: RequestInit): Promise<Response> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, {
      ...init,
      headers: { ...oturumBasliklari(), ...(init.headers as Record<string, string> | undefined) },
    });
  } catch {
    throw new KartUcHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = (await yanit.json().catch(() => null)) as { detail?: unknown } | null;
    throw hataCoz(yanit.status, govde?.detail);
  }
  return yanit;
}

function blobIndir(blob: Blob, ad: string): void {
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

function sorgu(p: Record<string, string | number | boolean | undefined | null>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v));
  const m = s.toString();
  return m ? `?${m}` : '';
}

export function kartApi(mod: PanelMod) {
  const T = mod === 'yonetici' ? '/api/v1/kartvizit/yonetim' : '/api/v1/kartvizitlerim';
  return {
    meta: () => istek<KartMeta>('GET', `${T}/meta`),
    liste: (p: { ara?: string; hesap?: string } = {}) =>
      istek<{ toplam: number; items: KartKaydi[] }>('GET', `${T}${sorgu(p)}`),
    getir: (id: number) => istek<KartKaydi>('GET', `${T}/${id}`),
    olustur: (g: Record<string, unknown>) => istek<KartKaydi>('POST', T, g),
    guncelle: (id: number, g: Record<string, unknown>) => istek<KartKaydi>('PUT', `${T}/${id}`, g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}`),
    slugUygun: (slug: string, haricId?: number, ad?: string) =>
      istek<SlugDurumu>('GET', `${T}/slug-uygun${sorgu({ slug, haric_id: haricId, ad })}`),
    analiz: (id: number, gun = 30) => istek<Analiz>('GET', `${T}/${id}/analiz?gun=${gun}`),
    async gorselYukle(id: number, tur: string, dosya: File): Promise<KartKaydi> {
      const form = new FormData();
      form.append('tur', tur);
      form.append('dosya', dosya);
      const y = await hamIstek(`${T}/${id}/gorsel`, { method: 'POST', body: form });
      return (await y.json()) as KartKaydi;
    },
    gorselKaldir: (id: number, gorselId: number) => istek<KartKaydi>('DELETE', `${T}/${id}/gorsel/${gorselId}`),
    galeriSira: (id: number, idler: number[]) => istek<KartKaydi>('PUT', `${T}/${id}/galeri-sira`, { idler }),
    async qrIndir(id: number, bicim: 'png' | 'svg', slug: string): Promise<void> {
      const y = await hamIstek(`${T}/${id}/qr?bicim=${bicim}`, { method: 'GET' });
      blobIndir(await y.blob(), `kartvizit-${slug}-qr.${bicim}`);
    },
    async qrBlob(id: number): Promise<Blob> {
      return (await hamIstek(`${T}/${id}/qr?bicim=svg`, { method: 'GET' })).blob();
    },
    mesajlar: (p: { kart_id?: number; okunmamis?: boolean; hesap?: string } = {}) =>
      istek<{ items: Mesaj[]; okunmamis: number }>('GET', `${T}/mesajlar${sorgu(p)}`),
    mesajOkundu: (id: number, okundu: boolean) => istek<Mesaj>('PUT', `${T}/mesajlar/${id}`, { okundu }),
    mesajSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/mesajlar/${id}`),
  };
}
export type KartApi = ReturnType<typeof kartApi>;

export function yorumApi(mod: PanelMod) {
  const T = mod === 'yonetici' ? '/api/v1/yorum-sayfalari/yonetim' : '/api/v1/yorum-sayfalarim';
  return {
    meta: () => istek<YorumMeta>('GET', `${T}/meta`),
    liste: (p: { ara?: string; hesap?: string } = {}) =>
      istek<{ toplam: number; items: YorumSayfasi[] }>('GET', `${T}${sorgu(p)}`),
    getir: (id: number) => istek<YorumSayfasi>('GET', `${T}/${id}`),
    olustur: (g: Record<string, unknown>) => istek<YorumSayfasi>('POST', T, g),
    guncelle: (id: number, g: Record<string, unknown>) => istek<YorumSayfasi>('PUT', `${T}/${id}`, g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}`),
    slugUygun: (slug: string, haricId?: number, ad?: string) =>
      istek<SlugDurumu>('GET', `${T}/slug-uygun${sorgu({ slug, haric_id: haricId, ad })}`),
    analiz: (id: number, gun = 30) => istek<Analiz>('GET', `${T}/${id}/analiz?gun=${gun}`),
    async logoYukle(id: number, dosya: File): Promise<YorumSayfasi> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(`${T}/${id}/logo`, { method: 'POST', body: form });
      return (await y.json()) as YorumSayfasi;
    },
    logoKaldir: (id: number) => istek<YorumSayfasi>('DELETE', `${T}/${id}/logo`),
    async qrIndir(id: number, bicim: 'png' | 'svg', slug: string): Promise<void> {
      const y = await hamIstek(`${T}/${id}/qr?bicim=${bicim}`, { method: 'GET' });
      blobIndir(await y.blob(), `yorum-${slug}-qr.${bicim}`);
    },
    async qrBlob(id: number): Promise<Blob> {
      return (await hamIstek(`${T}/${id}/qr?bicim=svg`, { method: 'GET' })).blob();
    },
    geriBildirimler: (p: { sayfa_id?: number; okunmamis?: boolean; hesap?: string } = {}) =>
      istek<{ items: Mesaj[]; okunmamis: number }>('GET', `${T}/geri-bildirimler${sorgu(p)}`),
    geriBildirimOkundu: (id: number, okundu: boolean) =>
      istek<{ ok: boolean }>('PUT', `${T}/geri-bildirimler/${id}`, { okundu }),
    geriBildirimSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/geri-bildirimler/${id}`),
  };
}
export type YorumApi = ReturnType<typeof yorumApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). Alan yolu (`webler.0.url`) gösteriliyor. */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof KartUcHatasi) {
    const metin = t(`kartvizit.hata.${e.kod}`, { ...e.ek, defaultValue: t('kartvizit.hata.genel') }) as string;
    return e.alan ? `${metin} (${alanAdi(t, e.alan)})` : metin;
  }
  return t('kartvizit.hata.genel');
}

/** `telefonlar.0.numara` → "Telefon 1 · numara" gibi okunur alan adı. */
export function alanAdi(t: TFunction, alan: string): string {
  const [kok, sira, alt] = alan.split('.');
  const ad = t(`kartvizit.alan.${kok}`, { defaultValue: kok }) as string;
  if (sira !== undefined && /^\d+$/.test(sira)) {
    return `${ad} ${Number(sira) + 1}${alt ? ` · ${t(`kartvizit.alan.${alt}`, { defaultValue: alt })}` : ''}`;
  }
  return ad;
}

export const BOS_SAATLER = (gunler: string[]): Saatler => ({
  goster: false,
  gunler: gunler.map((gun) => ({ gun, acik: !['cmt', 'paz'].includes(gun), acilis: '09:00', kapanis: '18:00' })),
  not: '',
});

export function bosIcerik(gunler: string[]): Icerik {
  return {
    ad_soyad: '',
    unvan: '',
    sirket: '',
    tanitim: '',
    telefonlar: [{ etiket: '', numara: '', tip: 'cep' }],
    eposta: '',
    webler: [],
    adres: '',
    harita_url: '',
    whatsapp: '',
    sosyal: [],
    baglantilar: [],
    hizmetler: [],
    calisma_saatleri: BOS_SAATLER(gunler),
  };
}

/** Türkçe harfleri sadeleştirerek addan slug önerisi (sunucu `slug_oner` ile aynı kural). */
export function slugOner(metin: string): string {
  const harf: Record<string, string> = { ı: 'i', İ: 'i', ş: 's', Ş: 's', ğ: 'g', Ğ: 'g', ü: 'u', Ü: 'u', ö: 'o', Ö: 'o', ç: 'c', Ç: 'c' };
  const m = (metin || '')
    .replace(/[ıİşŞğĞüÜöÖçÇ]/g, (c) => harf[c] || c)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
    .slice(0, 50)
    .replace(/-+$/g, '');
  return m.length >= 3 ? m : '';
}
