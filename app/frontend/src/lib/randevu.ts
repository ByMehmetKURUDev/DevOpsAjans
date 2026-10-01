import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';
import type { AtamaTuru, Haftalik, KonumTuru, RandevuDili, Soru, TelefonSecenegi } from '@/lib/randevuOrtak';

/**
 * Faz 5R — Randevu ve toplantılar: panel uçları.
 *
 * Yönetici `/api/v1/randevu/yonetim/...`, müşteri `/api/v1/randevularim/...`
 * (etkin hesap `X-MK-Hesap` başlığıyla). İki panel aynı bileşeni kullanıyor;
 * yalnız taban yol değişiyor. Bu dosya yalnız sekme açıldığında (lazy) iniyor.
 */

export type RandevuMod = 'yonetici' | 'musteri';

export interface Sayfa {
  id: number;
  hesap_email: string | null;
  slug: string;
  adres_url: string;
  baslik: string;
  karsilama: string;
  logo: string | null;
  renk: string;
  saat_dilimi: string;
  dil: RandevuDili;
  arama_motoru: boolean;
  tatilde_kapali: boolean;
  hatirlatmalar: number[];
  iptal_sinir_dk: number;
  saklama_gun: number;
  aktif: boolean;
  besleme_adresi: string;
  created_at: string | null;
  updated_at: string | null;
  yaklasan?: number;
  tur_sayisi?: number;
  tur_siniri?: number | null;
}

export interface Meta {
  yonetici: boolean;
  sayfa_siniri: number | null;
  tur_siniri: number | null;
  konum_turleri: KonumTuru[];
  atama_turleri: AtamaTuru[];
  telefon_secenekleri: TelefonSecenegi[];
  soru_turleri: Soru['tur'][];
  adimlar: number[];
  hatirlatma_secenekleri: number[];
  en_cok_hatirlatma: number;
  en_cok_soru: number;
  sure: [number, number];
  kapasite_en_cok: number;
  diller: RandevuDili[];
  adres_tabani: string;
  widget_adresi: string;
  varsayilan_saat_dilimi: string;
}

export interface Tur {
  id: number;
  sayfa_id: number;
  slug: string;
  ad: string;
  aciklama: string;
  sure_dk: number;
  adim_dk: number;
  konum_turu: KonumTuru;
  konum_degeri: string;
  tampon_once_dk: number;
  tampon_sonra_dk: number;
  en_erken_dk: number;
  en_gec_gun: number;
  gunluk_sinir: number | null;
  kapasite: number;
  telefon: TelefonSecenegi;
  sorular: Soru[];
  renk: string;
  atama: AtamaTuru;
  kisiler: number[];
  aktif: boolean;
  sira: number;
}

export interface Kisi {
  id: number;
  eposta: string;
  ad: string;
  haftalik: Haftalik;
  aktif: boolean;
  sira: number;
}

export interface Istisna {
  id: number;
  kisi_id: number | null;
  tarih: string;
  araliklar: [string, string][];
  aciklama: string;
}

export interface RandevuKaydi {
  id: number;
  uid: string;
  tur_id: number;
  tur_adi: string;
  tur_renk: string;
  konum_turu: KonumTuru | null;
  kisi_id: number;
  kisi_adi: string;
  baslangic: string;
  bitis: string;
  durum: 'onayli' | 'iptal';
  katilim: 'bilinmiyor' | 'geldi' | 'gelmedi';
  ad: string | null;
  eposta: string | null;
  telefon: string | null;
  yanitlar: { id: string; soru: string; yanit: string | boolean }[];
  konum: string | null;
  ziyaretci_tz: string | null;
  dil: string;
  iptal_eden: 'ziyaretci' | 'sahip' | null;
  iptal_nedeni: string | null;
  iptal_at: string | null;
  onceki_baslangic: string | null;
  anonim: boolean;
  crm_aday_id: number | null;
  created_at: string | null;
}

export interface Analiz {
  gun: number;
  goruntuleme: number;
  tekil: number;
  rezervasyon: number;
  iptal: number;
  donusum: number | null;
  katilim: Record<'bilinmiyor' | 'geldi' | 'gelmedi', number>;
  gunluk: { gun: string; goruntuleme: number; rezervasyon: number }[];
  turler: { id: number; ad: string; renk: string; goruntuleme: number; rezervasyon: number }[];
}

export class RandevuUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): RandevuUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new RandevuUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new RandevuUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new RandevuUcHatasi(durum, 'bulunamadi');
  return new RandevuUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new RandevuUcHatasi(0, 'ag');
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

export function randevuApi(mod: RandevuMod) {
  const T = mod === 'yonetici' ? '/api/v1/randevu/yonetim' : '/api/v1/randevularim';
  return {
    meta: () => istek<Meta>('GET', `${T}/meta`),
    liste: (hesap?: string) => istek<{ items: Sayfa[]; toplam: number }>('GET', `${T}${hesap ? `?hesap=${encodeURIComponent(hesap)}` : ''}`),
    olustur: (g: { baslik: string; slug?: string; hesap_email?: string; ad?: string; dil?: string }) => istek<Sayfa>('POST', T, g),
    getir: (id: number) => istek<Sayfa>('GET', `${T}/${id}`),
    guncelle: (id: number, g: Record<string, unknown>) => istek<Sayfa>('PUT', `${T}/${id}`, g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}`),
    async logoYukle(id: number, dosya: File): Promise<Sayfa> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(`${T}/${id}/logo`, { method: 'POST', body: form });
      return (await y.json()) as Sayfa;
    },
    logoSil: (id: number) => istek<Sayfa>('DELETE', `${T}/${id}/logo`),
    beslemeYenile: (id: number) => istek<Sayfa>('POST', `${T}/${id}/besleme/yenile`),
    async qrBlob(id: number, bicim: 'png' | 'svg', tur?: string): Promise<Blob> {
      const y = await hamIstek(`${T}/${id}/qr?bicim=${bicim}${tur ? `&tur=${encodeURIComponent(tur)}` : ''}`, { method: 'GET' });
      return y.blob();
    },
    analiz: (id: number, gun = 30) => istek<Analiz>('GET', `${T}/${id}/analiz?gun=${gun}`),
    turler: (id: number) => istek<{ items: Tur[]; tur_siniri: number | null }>('GET', `${T}/${id}/turler`),
    turOlustur: (id: number, g: Partial<Tur>) => istek<Tur>('POST', `${T}/${id}/turler`, g),
    turGuncelle: (id: number, tid: number, g: Partial<Tur>) => istek<Tur>('PUT', `${T}/${id}/turler/${tid}`, g),
    turSil: (id: number, tid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/turler/${tid}`),
    kisiler: (id: number) => istek<{ items: Kisi[]; adaylar: { eposta: string; ad: string }[] }>('GET', `${T}/${id}/kisiler`),
    kisiEkle: (id: number, g: { eposta: string; ad?: string }) => istek<Kisi>('POST', `${T}/${id}/kisiler`, g),
    kisiGuncelle: (id: number, kid: number, g: Partial<Kisi>) => istek<Kisi>('PUT', `${T}/${id}/kisiler/${kid}`, g),
    kisiSil: (id: number, kid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/kisiler/${kid}`),
    istisnalar: (id: number) => istek<{ items: Istisna[] }>('GET', `${T}/${id}/istisnalar`),
    istisnaEkle: (id: number, g: { tarih: string; kisi_id: number | null; araliklar: [string, string][]; aciklama?: string }) =>
      istek<Istisna>('POST', `${T}/${id}/istisnalar`, g),
    istisnaSil: (id: number, iid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/istisnalar/${iid}`),
    randevular: (id: number, q: { donem?: string; bas?: string; bit?: string } = {}) => {
      const p = new URLSearchParams();
      for (const [k, v] of Object.entries(q)) if (v) p.set(k, v);
      return istek<{ items: RandevuKaydi[]; toplam: number; saklama_gun: number }>('GET', `${T}/${id}/randevular?${p.toString()}`);
    },
    iptal: (id: number, rid: number, neden: string) => istek<RandevuKaydi>('POST', `${T}/${id}/randevular/${rid}/iptal`, { neden }),
    katilim: (id: number, rid: number, katilim: RandevuKaydi['katilim']) =>
      istek<RandevuKaydi>('PUT', `${T}/${id}/randevular/${rid}/katilim`, { katilim }),
  };
}

export type RandevuApi = ReturnType<typeof randevuApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof RandevuUcHatasi) {
    return t(`randevu.hata.${e.kod}`, { ...e.ek, defaultValue: t('randevu.hata.genel') }) as string;
  }
  return t('randevu.hata.genel');
}
