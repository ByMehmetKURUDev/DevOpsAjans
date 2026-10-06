import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { client } from '@/lib/sdkClient';

/**
 * Faz 5I — İçerik onayı (ajansın müşteri için hazırladığı içerik): küçük ortak katman.
 *
 * * Müşteri paneli "Onay bekleyen içerikler": `/api/v1/icerik-onaylarim` (oturumla; İçerik
 *   stüdyosu modülü kapalı olsa da çalışır — yalnız ekip izni `icerik`).
 * * Girişsiz sayfa `/icerik-onay/<jeton>`: düz `fetch` (jeton yetki; tek kullanımlık, süreli).
 *
 * Stüdyonun büyük katmanı (`lib/icerikStudyosu.ts`) bunu içe aktarıyor; tersi değil — panelin
 * üst kartı yalnız bu küçük dosyayı indirir.
 */

export type OnaySonucu = 'onay' | 'revizyon';

export interface Olcum {
  uzunluk: number;
  sinir: number | null;
  asim: boolean;
  hashtag?: number;
  hashtag_sinir?: number | null;
  hashtag_asim?: boolean;
}

export interface KanalOzeti {
  kanal: string;
  metin: string;
  baglanti: string | null;
  olcum: Olcum;
  ilk_yorum: string | null;
  gorsel_onerisi: { boyut: string; oran: string }[];
}

export interface Onizleme {
  id: number;
  baslik: string;
  kanallar: KanalOzeti[];
  gorseller: { url: string; ad: string; genislik?: number | null; yukseklik?: number | null }[];
  video_url: string;
  kampanya: string;
  marka_adi: string | null;
  saat_dilimi: string;
  planlanan: string | null;
  planlanan_at: string | null;
  durum: string;
}

export interface BekleyenOnay {
  islem_id: number;
  son_kullanma: string | null;
  gonderi: Onizleme;
}

export interface AcikOnay {
  durum: 'bekliyor' | 'kullanildi' | 'iptal' | 'suresi_doldu' | string;
  sonuc: OnaySonucu | null;
  sonuclar: OnaySonucu[];
  not_zorunlu: OnaySonucu[];
  son_kullanma: string | null;
  kullanildi_at: string | null;
  alici: string;
  gonderi: Onizleme | null;
}

export class OnayHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string
  ) {
    super(kod);
  }
}

function kodCoz(durum: number, detay: unknown): OnayHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    return new OnayHatasi(durum, (detay as { kod: string }).kod);
  }
  if (durum === 429) return new OnayHatasi(durum, 'cok_hizli');
  if (durum === 404) return new OnayHatasi(durum, 'bulunamadi');
  if (durum === 403) return new OnayHatasi(durum, 'yetki');
  return new OnayHatasi(durum, durum === 0 ? 'ag' : 'genel');
}

function govdeyiAc<T>(yanit: unknown): T {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T;
}

async function oturumlu<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    return govdeyiAc<T>(await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> | undefined }));
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    throw kodCoz(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

export const onaylarim = async (): Promise<BekleyenOnay[]> =>
  (await oturumlu<{ items: BekleyenOnay[] }>('GET', '/api/v1/icerik-onaylarim')).items || [];

export const onaylarimKarar = (gonderiId: number, sonuc: OnaySonucu, not?: string) =>
  oturumlu<{ durum: string; sonuc: string; gonderi_durumu: string }>('POST', `/api/v1/icerik-onaylarim/${gonderiId}`, {
    sonuc,
    not: not || null,
  });

async function acik<T>(jeton: string, govde?: Record<string, unknown>): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}/api/v1/icerik-onay/${encodeURIComponent(jeton)}`, {
      method: govde ? 'POST' : 'GET',
      headers: govde ? { 'Content-Type': 'application/json' } : undefined,
      body: govde ? JSON.stringify(govde) : undefined,
      referrerPolicy: 'no-referrer',
    });
  } catch {
    throw new OnayHatasi(0, 'ag');
  }
  const veri = (await yanit.json().catch(() => null)) as (T & { detail?: unknown }) | null;
  if (!yanit.ok) throw kodCoz(yanit.status, veri?.detail);
  return veri as T;
}

export const acikOnayGetir = (jeton: string) => acik<AcikOnay>(jeton);
export const acikOnayKarari = (jeton: string, sonuc: OnaySonucu, not?: string) =>
  acik<{ durum: string; sonuc: string }>(jeton, { sonuc, not: not || null });

export function onayHataMetni(t: TFunction, e: unknown): string {
  if (e instanceof OnayHatasi) return t(`icerikOnay.hata.${e.kod}`, { defaultValue: t('icerikOnay.hata.genel') }) as string;
  return t('icerikOnay.hata.genel');
}

/** Planlanan zaman: gönderinin saat diliminde (sunucunun yerel değeri) + kısaltılmış dilim adı. */
export function planlananYaz(o: { planlanan: string | null; planlanan_at: string | null; saat_dilimi: string }, dil: string): string {
  if (!o.planlanan_at) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short', timeZone: o.saat_dilimi }).format(new Date(o.planlanan_at));
  } catch {
    return (o.planlanan || '').replace('T', ' ');
  }
}

/** Platform metni karakter göstergesi: "123 / 2200". */
export function olcumYaz(o: Olcum | null | undefined, dil: string): string {
  if (!o) return '';
  const f = (n: number) => {
    try {
      return new Intl.NumberFormat(dil).format(n);
    } catch {
      return String(n);
    }
  };
  return o.sinir ? `${f(o.uzunluk)} / ${f(o.sinir)}` : f(o.uzunluk);
}
