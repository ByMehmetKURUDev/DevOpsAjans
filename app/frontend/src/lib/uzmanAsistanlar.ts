import type { TFunction } from 'i18next';

import { client } from '@/lib/sdkClient';

/**
 * Faz 3U — Uzman Asistanlar uçları.
 *
 * Müşteri `/api/v1/asistanlarim/...` (etkin hesap `X-MK-Hesap` başlığıyla —
 * istek katmanı ekliyor), yönetici `/api/v1/uzman-asistanlar/yonetim/...`.
 * Sistem istemi müşteriye hiç gelmiyor; model ve sınırlar sunucuda.
 * Asistan yanıtı markdown benzeri DÜZ METİN: arayüz HTML çizmiyor
 * (`components/asistanlar/GuvenliMarkdown.tsx`).
 *
 * Bu dosya yalnız sekmeler açıldığında (lazy parçalarda) iniyor.
 */

export const MESAJ_SINIRI = 8000;
export const CEVIRI_DILLERI = ['en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
export type CeviriDili = (typeof CEVIRI_DILLERI)[number];

export interface Asistan {
  anahtar: string;
  kategori: string;
  ad: string;
  aciklama: string;
  ornek_sorular: string[];
}

export interface Kategori {
  anahtar: string;
  ad: string;
}

export interface Kullanim {
  bugun: number;
  sinir: number;
  kalan: number;
}

export interface AsistanListesi {
  asistanlar: Asistan[];
  kategoriler: Kategori[];
  kullanim: Kullanim;
  kredi: { mesaj_basi: number; bakiye: number | null };
  kaynak: { ad: string; depo: string; lisans: string };
}

export interface Sohbet {
  id: number;
  asistan_anahtar: string;
  baslik: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AsistanMesaji {
  id: number;
  sohbet_id: number;
  rol: 'user' | 'assistant';
  icerik: string;
  created_at?: string | null;
}

export interface MesajYaniti {
  kullanici_mesaji: AsistanMesaji;
  asistan_mesaji: AsistanMesaji;
  sohbet: Sohbet;
  kullanim: Kullanim;
}

/** Sunucu hatası: `kod` ön yüzde yedi dilde metne çevriliyor (`uzmanAsistanlar.hata.<kod>`). */
export class AsistanUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

/** Hata → seçili dilde metin (`uzmanAsistanlar.hata.<kod>`; bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof AsistanUcHatasi) {
    return t(`uzmanAsistanlar.hata.${e.kod}`, { ...e.ek, defaultValue: t('uzmanAsistanlar.hata.genel') }) as string;
  }
  return t('uzmanAsistanlar.hata.genel');
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

function hataCoz(durum: number, detay: unknown): AsistanUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new AsistanUcHatasi(durum, kod, ek);
  }
  if (durum === 422) return new AsistanUcHatasi(durum, 'gecersiz');
  if (durum === 429) return new AsistanUcHatasi(durum, 'cok_hizli');
  return new AsistanUcHatasi(durum, 'genel');
}

async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    throw hataCoz(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

const M = '/api/v1/asistanlarim';
const Y = '/api/v1/uzman-asistanlar/yonetim';

// --- Müşteri ------------------------------------------------------------------
export const asistanlariGetir = (dil: string) =>
  istek<AsistanListesi>('GET', `${M}?dil=${encodeURIComponent(dil.slice(0, 2))}`);

export async function sohbetleriGetir(asistan?: string): Promise<Sohbet[]> {
  const g = await istek<{ sohbetler: Sohbet[] }>(
    'GET',
    `${M}/sohbetler${asistan ? `?asistan=${encodeURIComponent(asistan)}` : ''}`
  );
  return Array.isArray(g?.sohbetler) ? g.sohbetler : [];
}

export const sohbetAc = (asistanAnahtar: string) =>
  istek<Sohbet>('POST', `${M}/sohbetler`, { asistan_anahtar: asistanAnahtar });

export const sohbetGetir = (id: number) =>
  istek<{ sohbet: Sohbet; mesajlar: AsistanMesaji[] }>('GET', `${M}/sohbetler/${id}`);

export const mesajGonder = (id: number, icerik: string, yeniden = false) =>
  istek<MesajYaniti>('POST', `${M}/sohbetler/${id}/mesaj`, yeniden ? { icerik: '', yeniden: true } : { icerik });

export const sohbetSil = (id: number) => istek<{ ok: boolean }>('DELETE', `${M}/sohbetler/${id}`);

// --- Yönetici -----------------------------------------------------------------
export interface YonetimAsistani {
  id: number;
  anahtar: string;
  kategori: string;
  ad: string;
  aciklama: string;
  ornek_sorular: string[];
  ceviriler: Partial<Record<CeviriDili, { ad: string; aciklama: string; ornek_sorular: string[] }>>;
  sistem_istemi: string;
  aktif: boolean;
  sira: number;
  atif: string;
  updated_at?: string | null;
}

export interface AsistanAyarlari {
  asistan_model: string;
  asistan_max_tokens: number;
  asistan_gunluk_sinir: number;
  asistan_mesaj_kredi: number;
  ai_acik_gunluk_butce: number;
  ai_acik_model: string;
  varsayilan_model: string;
  etkin_model: string;
}

export interface YonetimVerisi {
  asistanlar: YonetimAsistani[];
  kategoriler: { anahtar: string; ad: Record<string, string> }[];
  ayarlar: AsistanAyarlari;
  kaynak: { ad: string; depo: string; commit: string; lisans: string; telif: string; lisans_metni: string };
}

export interface KullanimOzeti {
  gun: number;
  hesaplar: {
    hesap_email: string;
    kullanici_mesaji: number;
    asistan_mesaji: number;
    token_giris: number;
    token_cikis: number;
    son_mesaj_at: string | null;
  }[];
  asistanlar: { anahtar: string; asistan_mesaji: number }[];
  toplam: { kullanici_mesaji: number; asistan_mesaji: number; token_giris: number; token_cikis: number };
  gunluk: { gun: string; kapsam: string; istek: number; token_giris: number; token_cikis: number }[];
}

export const yonetimGetir = () => istek<YonetimVerisi>('GET', Y);

export const asistanGuncelle = (anahtar: string, govde: Partial<YonetimAsistani>) =>
  istek<YonetimAsistani>('PUT', `${Y}/${encodeURIComponent(anahtar)}`, govde as Record<string, unknown>);

export const ayarlariKaydet = (govde: Partial<AsistanAyarlari>) =>
  istek<AsistanAyarlari>('PUT', `${Y}/ayarlar`, govde as Record<string, unknown>);

export const kullanimGetir = (gun = 30) => istek<KullanimOzeti>('GET', `${Y}/kullanim?gun=${gun}`);

export const asistanDene = (anahtar: string, icerik: string, sistemIstemi?: string) =>
  istek<{ icerik: string; model: string; token_giris?: number | null; token_cikis?: number | null }>(
    'POST',
    `${Y}/${encodeURIComponent(anahtar)}/dene`,
    sistemIstemi ? { icerik, sistem_istemi: sistemIstemi } : { icerik }
  );
