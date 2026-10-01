import type { TFunction } from 'i18next';

import { client } from '@/lib/sdkClient';

/**
 * Faz 3B — Bağlantılar (Google: Analytics 4 + Search Console + YouTube).
 *
 * Yalnız yönetici. Uç ayrıntısı: `app/backend/routers/baglantilar.py`.
 * Hata gövdesi `{detail: {kod, ...}}` → `BaglantiUcHatasi(kod)`; metin
 * `baglantilar.hata.<kod>` (ek paket, 7 dil).
 */

export type GoogleDurumu = 'kurulmadi' | 'bagli_degil' | 'bagli' | 'yeniden_baglan';
export type KaynakKisa = 'ga4' | 'sc' | 'yt';

export interface Secimler {
  ga4_mulk: string | null;
  sc_site: string | null;
  yt_kanal: string | null;
}

export interface GoogleBaglantisi {
  saglayici: 'google';
  durum: GoogleDurumu;
  kurulum: { kurulu: boolean; eksik: string[]; gecersiz: string[] };
  harici_email: string | null;
  kapsamlar: Record<KaynakKisa, boolean>;
  secimler: Secimler;
  son_esitleme: string | null;
  son_deneme: string | null;
  son_hata: Record<string, string>;
  elle_bekleme_sn: number;
  baglanti_tarihi: string | null;
}

export interface YakindaSaglayici {
  saglayici: string;
  durum: 'yakinda';
}

export interface BaglantiDurumListesi {
  saglayicilar: (GoogleBaglantisi | YakindaSaglayici)[];
  yonlendirme_adresi: string;
  test_modu: boolean;
}

export interface KaynakSecenegi {
  kimlik: string;
  ad: string;
  yetki?: string;
}

export interface GoogleKaynaklari {
  ga4: KaynakSecenegi[];
  sc: KaynakSecenegi[];
  yt: KaynakSecenegi[];
  hatalar: Partial<Record<KaynakKisa, string>>;
}

export interface PanoSatiri {
  id: number | string;
  channel: string;
  metric_key: string;
  metric_label?: string | null;
  metric_value: number;
  change_pct?: number | null;
  unit?: string | null;
  snapshot_date?: string | null;
  kaynak?: string | null;
}

export interface PanoKanali {
  kanal: string;
  ornek: boolean;
  kaynaklar: string[];
  metrikler: PanoSatiri[];
  tarih: string | null;
}

export interface ListeSatiri {
  anahtar: string;
  tiklama: number;
  gosterim: number;
  to: number;
  sira: number;
}

export interface PanoVerisi {
  kanallar: PanoKanali[];
  yalniz_ornek: boolean;
  listeler: Partial<Record<'sorgular' | 'sayfalar', { kaynak: string; donem: [string, string]; satirlar: ListeSatiri[] }>>;
}

export class BaglantiUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof BaglantiUcHatasi) {
    return t(`baglantilar.hata.${e.kod}`, { ...e.ek, defaultValue: t('baglantilar.hata.genel') }) as string;
  }
  return t('baglantilar.hata.genel');
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

function hataCoz(durum: number, detay: unknown): BaglantiUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new BaglantiUcHatasi(durum, kod, ek);
  }
  return new BaglantiUcHatasi(durum, 'genel');
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

const K = '/api/v1/baglantilar';

export const durumGetir = () => istek<BaglantiDurumListesi>('GET', K);
export const panoGetir = () => istek<PanoVerisi>('GET', `${K}/pano`);
export const googleBaslat = () => istek<{ adres: string }>('POST', `${K}/google/baslat`);
export const googleKaynaklari = () => istek<GoogleKaynaklari>('GET', `${K}/google/kaynaklar`);
export const googleSecimKaydet = (secimler: Partial<Secimler>) =>
  istek<{ secimler: Secimler }>('PUT', `${K}/google/secim`, secimler as Record<string, unknown>);
export const googleEsitle = () =>
  istek<{ yazilan: number; kaynaklar: string[]; hatalar: Record<string, string>; durum: BaglantiDurumListesi }>(
    'POST',
    `${K}/google/esitle`
  );
export const googleKaldir = () => istek<{ silindi: boolean; iptal_edildi: boolean }>('DELETE', `${K}/google`);

export function googleBul(liste: BaglantiDurumListesi | null): GoogleBaglantisi | null {
  const g = liste?.saglayicilar.find((s) => s.saglayici === 'google');
  return g && g.durum !== 'yakinda' ? (g as GoogleBaglantisi) : null;
}
