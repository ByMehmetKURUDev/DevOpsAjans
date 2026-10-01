import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';
import type {
  Alerjen,
  CalismaSaatleri,
  Ceviriler,
  Duzen,
  Etiket,
  MenuDili,
  MenuGorsel,
  MenuKategori,
  MenuUrun,
  SecenekGrubu,
  SiparisAyarlari,
  Teslimat,
} from '@/lib/qrMenuOrtak';

/**
 * Faz 4M — QR menü ve WhatsApp katalog: panel uçları.
 *
 * Yönetici `/api/v1/qr-menu/yonetim/...`, müşteri `/api/v1/menulerim/...`
 * (etkin hesap `X-MK-Hesap` başlığıyla). İki panel aynı bileşeni kullanıyor;
 * yalnız taban yol değişiyor. Bu dosya yalnız sekme açıldığında (lazy) iniyor.
 */

export type MenuMod = 'yonetici' | 'musteri';

export interface Magaza {
  id: number;
  hesap_email: string | null;
  slug: string;
  adres_url: string;
  duzen: Duzen;
  ad: string;
  aciklama: string;
  ceviriler: Ceviriler;
  logo: MenuGorsel | null;
  kapak: MenuGorsel | null;
  tema_rengi: string;
  adres: string;
  telefon: string;
  whatsapp: string;
  calisma_saatleri: CalismaSaatleri;
  saat_dilimi: string;
  acik: boolean | null;
  para_birimi: string;
  varsayilan_dil: MenuDili;
  ek_diller: MenuDili[];
  siparis_ayarlari: SiparisAyarlari;
  saklama_gun: number;
  arama_motoru: boolean;
  aktif: boolean;
  created_at: string | null;
  updated_at: string | null;
  urun_sayisi?: number;
  yeni_siparis?: number;
  duzen_acik?: boolean;
}

export interface MenuMeta {
  duzenler: Duzen[];
  tum_duzenler: Duzen[];
  diller: MenuDili[];
  para_birimleri: string[];
  alerjenler: Alerjen[];
  etiketler: Etiket[];
  sinirlar: Record<Duzen, { magaza_siniri: number | null; magaza_sayisi: number | null; urun_siniri: number | null }>;
  ai_ceviri: boolean;
  gorsel_en_cok_mb: number;
  csv_en_cok_satir: number;
  menu_adres_tabani: string;
  en_cok_masa: number;
  yonetici: boolean;
}

export interface Icerik {
  kategoriler: MenuKategori[];
  urunler: MenuUrun[];
  urun_sayisi: number;
  urun_siniri: number | null;
}

export interface Kupon {
  id: number;
  kod: string;
  tur: 'yuzde' | 'tutar';
  deger: number;
  en_dusuk_tutar: number | null;
  baslangic: string | null;
  bitis: string | null;
  kullanim_siniri: number | null;
  kullanim_sayisi: number;
  aktif: boolean;
  durum: string;
}

export type SiparisDurumu = 'yeni' | 'hazirlaniyor' | 'teslim_edildi' | 'iptal';
export const SIPARIS_DURUMLARI: SiparisDurumu[] = ['yeni', 'hazirlaniyor', 'teslim_edildi', 'iptal'];

export interface Siparis {
  id: number;
  siparis_no: string;
  durum: SiparisDurumu;
  teslimat: Teslimat;
  masa: string | null;
  musteri_ad: string | null;
  adres: string | null;
  siparis_notu: string | null;
  anonim: boolean;
  kalemler: {
    urun_id: number;
    ad: string;
    ad_dil: string;
    adet: number;
    birim_fiyat: number;
    tutar: number;
    secenekler: { grup: string; ad: string; fiyat_farki: number }[];
  }[];
  ara_toplam: number;
  indirim: number;
  kupon_kodu: string | null;
  paket_ucreti: number;
  toplam: number;
  para_birimi: string;
  dil: string;
  created_at: string | null;
  magaza?: { ad: string; adres: string; telefon: string; para_birimi: string; varsayilan_dil: string };
}

export interface Analiz {
  gun: number;
  goruntuleme: number;
  tekil: number;
  urun_goruntuleme: number;
  sepete_ekleme: number;
  siparis: number;
  siparis_tutari: number;
  para_birimi: string;
  bot: number;
  gunluk: { gun: string; goruntuleme: number; tekil: number }[];
  en_cok_bakilan: { urun_id: number; ad: string; goruntuleme: number; sepet: number }[];
}

export interface IceAktarSatiri {
  satir: number;
  gecerli: boolean;
  hata: ({ kod: string; alan?: string } & Record<string, unknown>) | null;
  veri: {
    kategori: string;
    ad: string;
    aciklama: string;
    fiyat: number;
    indirimli_fiyat: number | null;
    etiketler: Etiket[];
    alerjenler: Alerjen[];
    kalori: number | null;
  } | null;
  ham: Record<string, string>;
}

export interface IceAktarOnizleme {
  satirlar: IceAktarSatiri[];
  toplam: number;
  gecerli: number;
  hatali: number;
  yeni_kategoriler: string[];
  kalan_hak: number | null;
}

export interface UrunGirdisi {
  kategori_id?: number;
  ad?: string;
  aciklama?: string;
  fiyat?: number | string;
  indirimli_fiyat?: number | string | null;
  gorsel?: string | null;
  secenek_gruplari?: SecenekGrubu[];
  etiketler?: Etiket[];
  alerjenler?: Alerjen[];
  kalori?: number | null;
  stokta_yok?: boolean;
  gizli?: boolean;
  ceviriler?: Ceviriler;
}

/** Sunucu hatası: `kod` yedi dilde metne çevriliyor (`qrMenu.hata.<kod>`). */
export class MenuUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): MenuUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new MenuUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new MenuUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new MenuUcHatasi(durum, 'bulunamadi');
  return new MenuUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new MenuUcHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = (await yanit.json().catch(() => null)) as { detail?: unknown } | null;
    throw hataCoz(yanit.status, govde?.detail);
  }
  return yanit;
}

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

export function menuApi(mod: MenuMod) {
  const T = mod === 'yonetici' ? '/api/v1/qr-menu/yonetim' : '/api/v1/menulerim';
  return {
    meta: () => istek<MenuMeta>('GET', `${T}/meta`),
    siparisOzeti: () => istek<{ yeni: number; magazalar: Record<string, number> }>('GET', `${T}/siparis-ozeti`),
    liste: (suzgec: { hesap?: string; ara?: string } = {}) => {
      const p = new URLSearchParams();
      if (suzgec.hesap) p.set('hesap', suzgec.hesap);
      if (suzgec.ara) p.set('ara', suzgec.ara);
      const q = p.toString();
      return istek<{ items: Magaza[]; toplam: number }>('GET', `${T}${q ? `?${q}` : ''}`);
    },
    olustur: (g: { ad: string; duzen: Duzen; slug?: string; hesap_email?: string }) => istek<Magaza>('POST', T, g),
    getir: (id: number) => istek<Magaza>('GET', `${T}/${id}`),
    guncelle: (id: number, g: Partial<Record<string, unknown>>) => istek<Magaza>('PUT', `${T}/${id}`, g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}`),
    icerik: (id: number) => istek<Icerik>('GET', `${T}/${id}/icerik`),
    kategoriOlustur: (id: number, g: Partial<MenuKategori> & { gorsel?: string | null }) =>
      istek<MenuKategori>('POST', `${T}/${id}/kategoriler`, g),
    kategoriGuncelle: (id: number, kid: number, g: Record<string, unknown>) =>
      istek<MenuKategori>('PUT', `${T}/${id}/kategoriler/${kid}`, g),
    kategoriSil: (id: number, kid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/kategoriler/${kid}`),
    kategoriSirala: (id: number, idler: number[]) => istek<{ ok: boolean }>('POST', `${T}/${id}/kategoriler/sirala`, { idler }),
    urunOlustur: (id: number, g: UrunGirdisi) => istek<MenuUrun>('POST', `${T}/${id}/urunler`, g),
    urunGuncelle: (id: number, uid: number, g: UrunGirdisi) => istek<MenuUrun>('PUT', `${T}/${id}/urunler/${uid}`, g),
    urunSil: (id: number, uid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/urunler/${uid}`),
    urunSirala: (id: number, idler: number[]) => istek<{ ok: boolean }>('POST', `${T}/${id}/urunler/sirala`, { idler }),
    async gorselYukle(id: number, dosya: File): Promise<MenuGorsel> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(`${T}/${id}/gorsel`, { method: 'POST', body: form });
      return (await y.json()) as MenuGorsel;
    },
    cevir: (id: number, g: { tur: 'magaza' | 'kategori' | 'urun'; id?: number; diller?: MenuDili[] }) =>
      istek<{ tur: string; diller: MenuDili[]; kayit: Magaza | MenuKategori | MenuUrun }>('POST', `${T}/${id}/ceviri`, g),
    kuponlar: (id: number) => istek<{ items: Kupon[] }>('GET', `${T}/${id}/kuponlar`),
    kuponOlustur: (id: number, g: Record<string, unknown>) => istek<Kupon>('POST', `${T}/${id}/kuponlar`, g),
    kuponGuncelle: (id: number, cid: number, g: Record<string, unknown>) => istek<Kupon>('PUT', `${T}/${id}/kuponlar/${cid}`, g),
    kuponSil: (id: number, cid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/kuponlar/${cid}`),
    siparisler: (id: number, durum?: string) =>
      istek<{ items: Siparis[]; toplam: number; yeni_sayisi: number; saklama_gun: number }>(
        'GET',
        `${T}/${id}/siparisler${durum ? `?durum=${durum}` : ''}`
      ),
    siparis: (id: number, sid: number) => istek<Siparis>('GET', `${T}/${id}/siparisler/${sid}`),
    siparisDurumu: (id: number, sid: number, durum: SiparisDurumu) =>
      istek<Siparis>('PUT', `${T}/${id}/siparisler/${sid}`, { durum }),
    analiz: (id: number, gun = 30) => istek<Analiz>('GET', `${T}/${id}/analiz?gun=${gun}`),
    async qrBlob(id: number, bicim: 'png' | 'svg', masa?: number): Promise<Blob> {
      const y = await hamIstek(`${T}/${id}/qr?bicim=${bicim}${masa ? `&masa=${masa}` : ''}`, { method: 'GET' });
      return y.blob();
    },
    async qrIndir(id: number, bicim: 'png' | 'svg', masa?: number): Promise<void> {
      const y = await hamIstek(`${T}/${id}/qr?bicim=${bicim}${masa ? `&masa=${masa}` : ''}`, { method: 'GET' });
      blobIndir(await y.blob(), dosyaAdi(y, `menu-qr.${bicim}`));
    },
    async masaZip(id: number, bas: number, bit: number, bicim: 'png' | 'svg'): Promise<void> {
      const y = await hamIstek(`${T}/${id}/masa-qr`, {
        method: 'POST',
        body: JSON.stringify({ bas, bit, bicim }),
        headers: { 'Content-Type': 'application/json' },
      });
      blobIndir(await y.blob(), dosyaAdi(y, `masalar-${bas}-${bit}.zip`));
    },
    async iceAktarOnizleme(id: number, dosya: File): Promise<IceAktarOnizleme> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(`${T}/${id}/ice-aktar/onizleme`, { method: 'POST', body: form });
      return (await y.json()) as IceAktarOnizleme;
    },
    iceAktar: (id: number, satirlar: IceAktarSatiri[]) =>
      istek<{ olusturulan: number; yeni_kategori: number; hatalar: ({ satir: number; kod: string } & Record<string, unknown>)[] }>(
        'POST',
        `${T}/${id}/ice-aktar`,
        { satirlar }
      ),
  };
}

export type MenuApi = ReturnType<typeof menuApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof MenuUcHatasi) {
    return t(`qrMenu.hata.${e.kod}`, { ...e.ek, defaultValue: t('qrMenu.hata.genel') }) as string;
  }
  return t('qrMenu.hata.genel');
}
