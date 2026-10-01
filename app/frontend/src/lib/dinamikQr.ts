import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 4Q — Dinamik QR stüdyosu ve kısa link uçları.
 *
 * Yönetici `/api/v1/dinamik-qr/yonetim/...`, müşteri `/api/v1/qr-kodlarim/...`
 * (etkin hesap `X-MK-Hesap` başlığıyla). İki panel aynı bileşeni kullanıyor;
 * yalnız taban yol değişiyor.
 *
 * Görseller (PNG/SVG/ZIP) oturumlu uçtan `fetch` ile alınıyor ve tarayıcıda
 * indiriliyor; önizleme SVG metni `<img src="data:...">` ile çiziliyor —
 * DOM'a HTML olarak hiç konmuyor.
 *
 * Bu dosya yalnız QR sekmesi açıldığında (lazy parçada) iniyor.
 */

export type QrMod = 'yonetici' | 'musteri';

export const TURLER = [
  'url',
  'google_yorum',
  'whatsapp',
  'telefon',
  'eposta',
  'sms',
  'konum',
  'vcard',
  'etkinlik',
  'uygulama',
  'wifi',
  'metin',
] as const;
export type QrTuru = (typeof TURLER)[number];
export const STATIK_TURLER: QrTuru[] = ['wifi', 'metin'];
export type QrDurumu = 'aktif' | 'pasif' | 'engelli' | 'suresi_doldu' | 'limit_doldu';
export const DURUMLAR: QrDurumu[] = ['aktif', 'pasif', 'engelli', 'suresi_doldu', 'limit_doldu'];

export interface Tasarim {
  on_renk: string;
  arka_renk: string;
  kenar: number;
  boyut: number;
  hata_duzeltme: 'L' | 'M' | 'Q' | 'H';
}

export type Alanlar = Record<string, string | boolean>;

export interface QrKaydi {
  id: number;
  kod: string;
  takma_ad: string | null;
  ad: string;
  tur: QrTuru;
  kisa_link: boolean;
  statik: boolean;
  alanlar: Alanlar;
  hedef_ozet: string;
  tasarim: Tasarim;
  logo_var: boolean;
  aktif: boolean;
  engelli: boolean;
  durum: QrDurumu;
  bitis: string | null;
  tarama_limiti: number | null;
  tarama_sayisi: number;
  son_tarama_at: string | null;
  kisa_adres: string | null;
  qr_adresi: string | null;
  hesap_email: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface QrMeta {
  turler: QrTuru[];
  kisa_adres_tabani: string;
  tasarim: Tasarim;
  boyut: { en_az: number; en_cok: number };
  logo_en_cok_kb: number;
  csv_en_cok_satir: number;
  csv_en_cok_kb: number;
  kayit_siniri: number | null;
  kayit_sayisi: number | null;
  yonetici: boolean;
}

export interface Onizleme {
  svg: string;
  uyarilar: string[];
  kontrast: number;
  surum: number;
  hata_duzeltme: string;
}

export interface Dagilim {
  anahtar: string | null;
  sayi: number;
}

export interface Analiz {
  statik: boolean;
  toplam: number;
  tekil: number;
  bot: number;
  donem: { gun: number; tarama: number; tekil: number };
  gunluk: { gun: string; tarama: number; tekil: number }[];
  ulkeler: Dagilim[];
  cihazlar: Dagilim[];
  isletim: Dagilim[];
  refererlar: Dagilim[];
  son_tarama_at: string | null;
}

export interface TopluSatir {
  satir: number;
  ad: string;
  tur: string;
  alanlar: Alanlar;
  kisa_link: boolean;
  takma_ad: string | null;
  gecerli: boolean;
  hata: { kod: string; alan?: string } | null;
  hedef_ozet: string;
}

export interface TopluOnizleme {
  satirlar: TopluSatir[];
  toplam: number;
  gecerli: number;
  hatali: number;
  kalan_hak: number | null;
}

/** Kaydet/önizle gövdesi. */
export interface QrGirdisi {
  ad?: string;
  tur?: QrTuru;
  alanlar?: Alanlar;
  tasarim?: Partial<Tasarim>;
  kisa_link?: boolean;
  takma_ad?: string | null;
  aktif?: boolean;
  bitis?: string | null;
  tarama_limiti?: number | null;
  logo?: string;
  logo_kaldir?: boolean;
  hesap_email?: string;
  qr_id?: number;
}

/** Sunucu hatası: `kod` yedi dilde metne çevriliyor (`dinamikQr.hata.<kod>`). */
export class QrUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): QrUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new QrUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new QrUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new QrUcHatasi(durum, 'bulunamadi');
  return new QrUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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

function jeton(): string | null {
  try {
    return localStorage.getItem('token');
  } catch {
    return null;
  }
}

function oturumBasliklari(): Record<string, string> {
  const b: Record<string, string> = { ...hesapBasliklari() };
  const j = jeton();
  if (j) b.Authorization = `Bearer ${j}`;
  return b;
}

/** Oturumlu ham istek (dosya indirme / çok parçalı yükleme). */
async function hamIstek(url: string, init: RequestInit): Promise<Response> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, {
      ...init,
      headers: { ...oturumBasliklari(), ...(init.headers as Record<string, string> | undefined) },
    });
  } catch {
    throw new QrUcHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = (await yanit.json().catch(() => null)) as { detail?: unknown } | null;
    throw hataCoz(yanit.status, govde?.detail);
  }
  return yanit;
}

/** Content-Disposition'dan dosya adı (RFC 6266 `filename*` önce). */
function dosyaAdi(yanit: Response, yedek: string): string {
  const baslik = yanit.headers.get('content-disposition') || '';
  const utf = /filename\*=UTF-8''([^;]+)/i.exec(baslik);
  if (utf) {
    try {
      return decodeURIComponent(utf[1]);
    } catch {
      /* düz ada düş */
    }
  }
  const duz = /filename="([^"]+)"/i.exec(baslik);
  return duz ? duz[1] : yedek;
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

export function qrApi(mod: QrMod) {
  const T = mod === 'yonetici' ? '/api/v1/dinamik-qr/yonetim' : '/api/v1/qr-kodlarim';
  return {
    meta: () => istek<QrMeta>('GET', `${T}/meta`),
    liste: (suzgec: { tur?: string; kisa?: boolean; durum?: string; ara?: string; hesap?: string } = {}) => {
      const p = new URLSearchParams();
      if (suzgec.tur) p.set('tur', suzgec.tur);
      if (suzgec.kisa !== undefined) p.set('kisa', String(suzgec.kisa));
      if (suzgec.durum) p.set('durum', suzgec.durum);
      if (suzgec.ara) p.set('ara', suzgec.ara);
      if (suzgec.hesap) p.set('hesap', suzgec.hesap);
      p.set('sinir', '500');
      return istek<{ toplam: number; items: QrKaydi[] }>('GET', `${T}?${p.toString()}`);
    },
    getir: (id: number) => istek<QrKaydi>('GET', `${T}/${id}`),
    olustur: (g: QrGirdisi) => istek<QrKaydi>('POST', T, g),
    guncelle: (id: number, g: QrGirdisi) => istek<QrKaydi>('PUT', `${T}/${id}`, g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}`),
    engelle: (id: number, engelli: boolean) =>
      istek<QrKaydi>('POST', `/api/v1/dinamik-qr/yonetim/${id}/engelle`, { engelli }),
    onizleme: (g: QrGirdisi) => istek<Onizleme>('POST', `${T}/onizleme`, g),
    analiz: (id: number, gun = 30) => istek<Analiz>('GET', `${T}/${id}/analiz?gun=${gun}`),
    topluOlustur: (satirlar: TopluSatir[], tasarim?: Partial<Tasarim>) =>
      istek<{ olusturulan: QrKaydi[]; hatalar: ({ satir: number; kod: string } & Record<string, unknown>)[] }>(
        'POST',
        `${T}/toplu/olustur`,
        { satirlar, tasarim }
      ),
    async topluOnizleme(dosya: File): Promise<TopluOnizleme> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(`${T}/toplu/onizleme`, { method: 'POST', body: form });
      return (await y.json()) as TopluOnizleme;
    },
    /** Kaydın görseli (önizleme için blob). */
    async gorselBlob(id: number, bicim: 'png' | 'svg'): Promise<Blob> {
      const y = await hamIstek(`${T}/${id}/gorsel?bicim=${bicim}`, { method: 'GET' });
      return y.blob();
    },
    async gorselIndir(id: number, bicim: 'png' | 'svg', kod: string): Promise<void> {
      const y = await hamIstek(`${T}/${id}/gorsel?bicim=${bicim}`, { method: 'GET' });
      blobIndir(await y.blob(), dosyaAdi(y, `qr-${kod}.${bicim}`));
    },
    async zipIndir(idler: number[], bicim: 'png' | 'svg'): Promise<void> {
      const y = await hamIstek(`${T}/zip`, {
        method: 'POST',
        body: JSON.stringify({ idler, bicim }),
        headers: { 'Content-Type': 'application/json' },
      });
      blobIndir(await y.blob(), dosyaAdi(y, `qr-kodlari-${bicim}.zip`));
    },
  };
}

export type QrApi = ReturnType<typeof qrApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof QrUcHatasi) {
    return t(`dinamikQr.hata.${e.kod}`, { ...e.ek, defaultValue: t('dinamikQr.hata.genel') }) as string;
  }
  return t('dinamikQr.hata.genel');
}

/** SVG metni → `<img>` için data adresi (DOM'a HTML konmuyor). */
export function svgAdresi(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/** Dosyayı data: adresine çevirir (logo yükleme). */
export function dosyaOku(dosya: File): Promise<string> {
  return new Promise((coz, reddet) => {
    const okuyucu = new FileReader();
    okuyucu.onload = () => coz(String(okuyucu.result || ''));
    okuyucu.onerror = () => reddet(okuyucu.error);
    okuyucu.readAsDataURL(dosya);
  });
}

/** Alanlardan UTM eklenmiş hedef (yalnız gösterim; asıl hesap sunucuda). */
export function utmOnizleme(url: string, a: Alanlar): string {
  const temiz = (url || '').trim();
  if (!temiz) return '';
  try {
    const u = new URL(/^[a-z][a-z0-9+.-]*:/i.test(temiz) ? temiz : `https://${temiz}`);
    for (const k of ['utm_source', 'utm_medium', 'utm_campaign']) {
      const v = String(a[k] || '').trim();
      if (v) u.searchParams.set(k, v);
    }
    return u.toString();
  } catch {
    return temiz;
  }
}
