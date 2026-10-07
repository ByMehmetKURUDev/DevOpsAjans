import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 6P — Stok ve satış noktası (POS): panel uçları ve küçük yardımcılar.
 *
 * Müşteri paneli `/api/v1/stok-pos/...` (etkin hesap = işletme; `X-MK-Hesap`), ajans paneli
 * `/api/v1/stok-pos-yonetim/...?hesap=` (salt okunur destek görünümü). Tutarlar sunucudan kuruş (tam
 * sayı), miktarlar sayı (kg/lt kesirli). Bu dosya yalnız sekme açıldığında (lazy) iniyor.
 */

export type StokMod = 'musteri' | 'yonetici';
export type OdemeTuru = 'nakit' | 'kart' | 'havale' | 'karma';
export type Birim = 'adet' | 'kg' | 'lt' | 'm' | 'paket';

export interface Konum {
  id: number;
  ad: string;
  adres: string | null;
  varsayilan: boolean;
  aktif: boolean;
  sira: number;
}

export interface Ayarlar {
  firma_adi: string | null;
  adres: string | null;
  telefon: string | null;
  eposta: string | null;
  vergi_dairesi: string | null;
  vergi_no: string | null;
  para_birimi: string;
  kdv_oranlari: number[];
  kdv_varsayilan: boolean;
  varsayilan_kdv: number;
  eksi_stok: boolean;
  kasa_iade: boolean;
  kasa_indirim_yuzde: number;
  qr_stok_esitle: boolean;
  kritik_bildirim: boolean;
  fis_notu: string | null;
}

export interface Oturum {
  id: number;
  konum_id: number;
  durum: 'acik' | 'kapali';
  acan: string;
  acilis_at: string;
  acilis_nakit: number;
  kapatan: string | null;
  kapanis_at: string | null;
  sayilan_nakit: number | null;
  beklenen_nakit: number | null;
  fark: number | null;
  notlar: string | null;
  /** Faz 6Q: "esitleme" = kapanmış oturuma geç gelen çevrimdışı satışların oturumu. */
  tur?: 'kasa' | 'esitleme';
  kaynak_oturum_id?: number | null;
}

export interface Meta {
  hesap: string;
  ben: string;
  yetki: { stok: boolean; kasa: boolean; ajans: boolean };
  salt_okunur: boolean;
  ayarlar: Ayarlar;
  varsayilan_kdv_oranlari: number[];
  birimler: Birim[];
  odeme_turleri: OdemeTuru[];
  hareket_turleri: string[];
  elle_hareketler: string[];
  konumlar: Konum[];
  sinirlar: { urun: number; sube: number; kasa_kullanici: number };
  sayilar: { urun: number; kritik: number };
  acik_oturumlar: Oturum[];
  qr_menu: boolean;
  /** Faz 6Q: saha servisi modülü açık → stok raporlarında "saha servisi tüketimi". */
  saha?: boolean;
  hareket_kaynaklari?: string[];
  notlar: { fis: string; z: string };
}

export interface Urun {
  id: number;
  ad: string;
  barkod: string;
  barkod_turu: 'ean13' | 'ean8' | 'code128';
  sku: string | null;
  kategori: string | null;
  birim: Birim;
  satis_fiyati: number;
  alis_fiyati?: number;
  kdv_orani: number;
  kritik_esik: number | null;
  stok_takibi: boolean;
  ana_urun_id: number | null;
  varyant: { beden?: string; renk?: string } | null;
  menu_urun_id: number | null;
  aktif: boolean;
  notlar: string | null;
  stok: { toplam: number; konumlar: Record<string, number> };
  kritik: boolean;
  varyantlar?: Urun[];
  hareketler?: Hareket[];
}

export interface Hareket {
  id: number;
  urun_id: number;
  urun_ad: string | null;
  konum_id: number;
  tur: string;
  miktar: number;
  sonra: number | null;
  birim_maliyet: number | null;
  tedarikci_id: number | null;
  satis_id: number | null;
  sayim_id: number | null;
  transfer_kodu: string | null;
  belge_no: string | null;
  aciklama: string | null;
  kisi: string | null;
  zaman: string;
  kaynak?: string | null;
  kaynak_id?: number | null;
}

export interface Tedarikci {
  id: number;
  ad: string;
  yetkili: string | null;
  telefon: string | null;
  eposta: string | null;
  vergi_no: string | null;
  notlar: string | null;
  aktif: boolean;
}

export interface Alici {
  id: number;
  tur: 'bireysel' | 'kurumsal';
  ad: string;
  vergi_dairesi: string | null;
  vergi_no: string | null;
  adres: string | null;
  eposta: string | null;
  telefon: string | null;
}

export interface KdvSatiri {
  oran: number;
  tutar: number;
  matrah: number;
  kdv: number;
}

export interface SatisKalemi {
  id: number;
  urun_id: number;
  ad: string;
  barkod: string | null;
  birim: Birim;
  adet: number;
  adet_binde: number;
  birim_fiyat: number;
  brut: number;
  satir_indirim: number;
  indirim: number;
  tutar: number;
  kdv_orani: number;
  kdv: number;
  iade_adet: number;
  iade_adet_binde: number;
  iade_tutar: number;
}

export interface SatisOzeti {
  id: number;
  no: string;
  durum: 'tamamlandi' | 'kismi_iade' | 'iade' | 'iptal';
  zaman: string;
  konum_id: number;
  oturum_id: number;
  kasiyer: string;
  musteri_ad: string | null;
  toplam: number;
  iade_toplam: number;
  odeme_turu: OdemeTuru;
  fatura_no: string | null;
  para_birimi: string;
  /** Faz 6Q: çevrimdışı kuyruktan eşitlenen satış (cihazda basılan "ÇEVRİMDIŞI-n" ve sunucuya ulaştığı an). */
  cevrimdisi_no?: string | null;
  esitlendi_at?: string | null;
}

export interface Satis extends SatisOzeti {
  tarih_metni: string;
  alici_id: number | null;
  ara_toplam: number;
  satir_indirim: number;
  toplam_indirim: number;
  kdv_toplam: number;
  kdv_dokumu: KdvSatiri[];
  nakit: number;
  kart: number;
  havale: number;
  nakit_alinan: number;
  para_ustu: number;
  notlar: string | null;
  fatura_at: string | null;
  fatura_alici: Partial<Alici> | null;
  kalemler: SatisKalemi[];
  iadeler: { id: number; tur: 'iade' | 'iptal'; tutar: number; odeme_turu: string; neden: string | null; kisi: string | null; zaman: string }[];
  firma: { ad: string | null; adres: string | null; telefon: string | null; eposta: string | null; vergi_dairesi: string | null; vergi_no: string | null; fis_notu: string | null };
  mali_degil: string;
  tekrar?: boolean;
  kritik?: number[];
  eksi_stok?: { urun_id: number; ad: string; birim: Birim; miktar: number }[];
  /** Yalnız cihazda: kuyruğa alınmış, henüz eşitlenmemiş fiş. */
  yerel?: boolean;
}

export interface Ozet {
  satis_sayisi: number;
  brut: number;
  indirim: number;
  satis_toplam: number;
  iade_sayisi: number;
  iade_toplam: number;
  iptal_sayisi: number;
  iptal_toplam: number;
  net: number;
  /** Faz 6Q: çevrimdışı kuyruktan eşitlenen satışlar (eski donmuş Z'lerde yok). */
  cevrimdisi_sayisi?: number;
  cevrimdisi_toplam?: number;
  odemeler: { nakit: number; kart: number; havale: number };
  kdv_dokumu: KdvSatiri[];
  en_cok_satanlar: { urun_id: number; ad: string; birim: Birim; adet: number; tutar: number }[];
  para_birimi: string;
  nakit?: { acilis: number; satis: number; iade: number; beklenen: number; sayilan: number | null; fark: number | null };
  oturumlar?: Oturum[];
  tarih?: string;
}

export interface SayimSatiri {
  urun_id: number;
  ad: string;
  barkod: string | null;
  birim: Birim;
  sayilan: number;
  sistem: number;
  fark: number;
  zaman?: string;
}

export interface Sayim {
  id: number;
  konum_id: number;
  durum: 'acik' | 'onaylandi' | 'iptal';
  aciklama: string | null;
  baslatan: string | null;
  onaylayan: string | null;
  baslangic: string;
  bitis: string | null;
  ozet: { kalem: number; farkli: number; fark_arti: number; fark_eksi: number; deger_farki: number } | null;
  kalemler?: SayimSatiri[];
}

export interface SepetKalemi {
  urun_id: number;
  ad: string;
  barkod: string;
  birim: Birim;
  birim_fiyat: number;
  kdv_orani: number;
  adet: number;
  /** Kuruş. */
  indirim: number;
}

// ---------------------------------------------------------------------------
// Hata
// ---------------------------------------------------------------------------
export class StokHatasi extends Error {
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

function hataCoz(durum: number, detay: unknown): StokHatasi {
  if (detay && typeof detay === 'object' && 'kod' in (detay as Record<string, unknown>)) {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new StokHatasi(durum, String(kod), ek);
  }
  if (durum === 429) return new StokHatasi(durum, 'cok_hizli');
  if (durum === 404) return new StokHatasi(durum, 'bulunamadi');
  if (durum === 403) return new StokHatasi(durum, 'yetki_yok');
  return new StokHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new StokHatasi(0, 'ag');
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

export function stokApi(mod: StokMod, hesap?: string) {
  const T = mod === 'yonetici' ? '/api/v1/stok-pos-yonetim' : '/api/v1/stok-pos';
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
    hesaplar: () =>
      istek<{ items: { hesap_email: string; firma_adi: string | null; urun: number; satis: number }[] }>('GET', '/api/v1/stok-pos-yonetim/hesaplar'),
    meta: () => istek<Meta>('GET', u('/meta')),
    ayarlarKaydet: (g: Partial<Ayarlar> | Record<string, unknown>) => istek<Ayarlar>('PUT', u('/ayarlar'), g),
    konumEkle: (g: { ad: string; adres?: string }) => istek<Konum>('POST', u('/konumlar'), g),
    konumGuncelle: (id: number, g: Partial<Konum>) => istek<Konum>('PUT', u(`/konumlar/${id}`), g),
    konumSil: (id: number) => istek<{ ok: boolean; pasif: boolean }>('DELETE', u(`/konumlar/${id}`)),
    urunler: (q: { ara?: string; kategori?: string; kritik?: boolean; aktif?: string; sayfa?: number; adet?: number } = {}) =>
      istek<{ items: Urun[]; toplam: number; sayfa: number; kategoriler: string[] }>('GET', u('/urunler', q)),
    urunKodla: (kod: string) => istek<Urun>('GET', u(`/urunler/kod/${encodeURIComponent(kod)}`)),
    urun: (id: number) => istek<Urun>('GET', u(`/urunler/${id}`)),
    urunEkle: (g: Record<string, unknown>) => istek<Urun>('POST', u('/urunler'), g),
    urunGuncelle: (id: number, g: Record<string, unknown>) => istek<Urun>('PUT', u(`/urunler/${id}`), g),
    urunSil: (id: number) => istek<{ ok: boolean; pasif: boolean }>('DELETE', u(`/urunler/${id}`)),
    varyantEkle: (id: number, g: Record<string, unknown>) => istek<Urun>('POST', u(`/urunler/${id}/varyant`), g),
    barkodUret: () => istek<{ barkod: string }>('POST', u('/barkod-uret')),
    urunlerCsv: () => indir('/urunler.csv', {}, 'urunler.csv'),
    async iceAktar(dosya: File): Promise<{ eklenen: number; guncellenen: number; hata_sayisi: number; hatalar: { satir: number; kod: string }[] }> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(u('/urunler/ice-aktar'), { method: 'POST', body: form });
      return y.json();
    },
    menuKaynaklari: () => istek<{ items: { id: number; ad: string; duzen: string; slug: string; urun: number; bagli: number }[] }>('GET', u('/menu-kaynaklari')),
    menudenAktar: (magaza_id: number) => istek<{ eklenen: number; guncellenen: number }>('POST', u('/menuden-aktar'), { magaza_id }),
    tedarikciler: () => istek<{ items: Tedarikci[] }>('GET', u('/tedarikciler')),
    tedarikciEkle: (g: Partial<Tedarikci>) => istek<Tedarikci>('POST', u('/tedarikciler'), g),
    tedarikciGuncelle: (id: number, g: Partial<Tedarikci>) => istek<Tedarikci>('PUT', u(`/tedarikciler/${id}`), g),
    tedarikciSil: (id: number) => istek<{ ok: boolean; pasif: boolean }>('DELETE', u(`/tedarikciler/${id}`)),
    hareketler: (q: { urun_id?: number; konum_id?: number; tur?: string; kaynak?: string; bas?: string; bit?: string; sayfa?: number } = {}) =>
      istek<{ items: Hareket[]; toplam: number; sayfa: number }>('GET', u('/hareketler', q)),
    hareketEkle: (g: Record<string, unknown>) => istek<{ ok: boolean; kalem: number; kritik: number[] }>('POST', u('/hareketler'), g),
    transfer: (g: Record<string, unknown>) => istek<{ ok: boolean; transfer_kodu: string }>('POST', u('/transfer'), g),
    sayimlar: () => istek<{ items: Sayim[] }>('GET', u('/sayimlar')),
    sayim: (id: number) => istek<Sayim>('GET', u(`/sayimlar/${id}`)),
    sayimBaslat: (g: { konum_id?: number; aciklama?: string }) => istek<Sayim>('POST', u('/sayimlar'), g),
    sayimOkut: (id: number, g: Record<string, unknown>) => istek<SayimSatiri>('POST', u(`/sayimlar/${id}/okut`), g),
    sayimOnayla: (id: number, sayilmayanlar_sifir: boolean) => istek<Sayim>('POST', u(`/sayimlar/${id}/onayla`), { sayilmayanlar_sifir }),
    sayimIptal: (id: number) => istek<Sayim>('POST', u(`/sayimlar/${id}/iptal`)),
    kasa: () => istek<{ acik: Oturum[]; son: Oturum[] }>('GET', u('/kasa')),
    kasaAc: (g: { konum_id: number; acilis_nakit: number | string }) => istek<Oturum>('POST', u('/kasa/ac'), g),
    kasaOzeti: (id: number) => istek<{ oturum: Oturum; ozet: Ozet; not: string }>('GET', u(`/kasa/${id}`)),
    kasaKapat: (id: number, g: { sayilan_nakit: number | string; notlar?: string }) =>
      istek<{ oturum: Oturum; ozet: Ozet; not: string }>('POST', u(`/kasa/${id}/kapat`), g),
    satislar: (q: { oturum_id?: number; bas?: string; bit?: string; ara?: string; sayfa?: number } = {}) =>
      istek<{ items: SatisOzeti[]; toplam: number; sayfa: number }>('GET', u('/satislar', q)),
    satis: (id: number) => istek<Satis>('GET', u(`/satislar/${id}`)),
    satisEkle: (g: Record<string, unknown>) => istek<Satis>('POST', u('/satislar'), g),
    iade: (id: number, g: Record<string, unknown>) => istek<Satis>('POST', u(`/satislar/${id}/iade`), g),
    iptal: (id: number, g: Record<string, unknown> = {}) => istek<Satis>('POST', u(`/satislar/${id}/iptal`), g),
    faturaKes: (id: number, g: Record<string, unknown>) => istek<Satis>('POST', u(`/satislar/${id}/fatura`), g),
    fisPdf: (s: { id: number; no: string }, dil?: string) => indir(`/satislar/${s.id}/fis.pdf`, { dil }, `fis-${s.no}.pdf`),
    faturaPdf: (s: { id: number; fatura_no: string | null }, dil?: string) =>
      indir(`/satislar/${s.id}/fatura.pdf`, { dil }, `fatura-${s.fatura_no || s.id}.pdf`),
    alicilar: (ara?: string) => istek<{ items: Alici[] }>('GET', u('/alicilar', { ara })),
    aliciEkle: (g: Partial<Alici>) => istek<Alici>('POST', u('/alicilar'), g),
    raporGun: (tarih?: string, konum_id?: number) => istek<Ozet & { not: string }>('GET', u('/raporlar/gun', { tarih, konum_id })),
    raporDonem: (bas: string, bit: string, konum_id?: number) =>
      istek<{ gunler: ({ tarih: string; net: number } & Record<string, number>)[]; toplam: Record<string, number> }>('GET', u('/raporlar/donem', { bas, bit, konum_id })),
    raporKar: (bas: string, bit: string, konum_id?: number) =>
      istek<{ urunler: { urun_id: number; ad: string; birim: Birim; adet: number; ciro: number; maliyet: number; kar: number; marj: number | null }[]; toplam: { ciro: number; maliyet: number; kar: number; marj: number | null } }>(
        'GET',
        u('/raporlar/kar', { bas, bit, konum_id })
      ),
    raporStokDegeri: (konum_id?: number) =>
      istek<{ urunler: { urun_id: number; ad: string; barkod: string; birim: Birim; miktar: number; maliyet_degeri: number; satis_degeri: number; eksi: boolean }[]; toplam: { maliyet_degeri: number; satis_degeri: number; urun: number; eksi: number } }>(
        'GET',
        u('/raporlar/stok-degeri', { konum_id })
      ),
    raporHareketsiz: (gun: number) =>
      istek<{ urunler: { urun_id: number; ad: string; barkod: string; birim: Birim; miktar: number; son_satis: string | null; gun: number | null; maliyet_degeri: number }[]; toplam: { urun: number; maliyet_degeri: number } }>(
        'GET',
        u('/raporlar/hareketsiz', { gun })
      ),
    raporSahaTuketimi: (bas: string, bit: string, konum_id?: number) =>
      istek<{ urunler: { urun_id: number; ad: string; barkod: string | null; birim: Birim; miktar: number; maliyet: number; is_emri: number }[]; toplam: { urun: number; maliyet: number; is_emri: number } }>(
        'GET',
        u('/raporlar/saha-tuketimi', { bas, bit, konum_id })
      ),
    raporCsv: (tur: 'donem' | 'kar' | 'stok-degeri' | 'hareketsiz' | 'saha-tuketimi', q: Sorgu) => indir(`/raporlar/${tur}`, { ...q, bicim: 'csv' }, `${tur}.csv`),
  };
}

export type StokApi = ReturnType<typeof stokApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof StokHatasi) {
    return t(`stokPos.hata.${e.kod}`, { ...e.ek, defaultValue: t('stokPos.hata.genel') }) as string;
  }
  return t('stokPos.hata.genel');
}

// ---------------------------------------------------------------------------
// Biçim
// ---------------------------------------------------------------------------
function yerelAd(dil: string): string {
  return dil === 'ar' ? 'ar-u-nu-latn' : dil;
}

/** Kuruş → para metni (Intl.NumberFormat). */
export function para(kurus: number | null | undefined, birim: string, dil: string): string {
  const tutar = (kurus || 0) / 100;
  try {
    return new Intl.NumberFormat(yerelAd(dil), { style: 'currency', currency: birim || 'TRY', currencyDisplay: 'narrowSymbol' }).format(tutar);
  } catch {
    return `${tutar.toFixed(2)} ${birim}`;
  }
}

export function miktarYaz(m: number | null | undefined, dil: string): string {
  if (m === null || m === undefined) return '—';
  try {
    return new Intl.NumberFormat(yerelAd(dil), { maximumFractionDigits: 3 }).format(m);
  } catch {
    return String(m);
  }
}

/** "12,50" / "12.5" → kuruş; geçersizse null. */
export function kurusaCevir(metin: string): number | null {
  const s = metin.trim().replace(/\s|₺|TL/gi, '');
  if (!s) return null;
  let n = s;
  if (n.includes(',') && n.includes('.')) n = n.lastIndexOf(',') > n.lastIndexOf('.') ? n.replace(/\./g, '').replace(',', '.') : n.replace(/,/g, '');
  else n = n.replace(',', '.');
  const d = Number(n);
  return Number.isFinite(d) && d >= 0 ? Math.round(d * 100) : null;
}

export function sayiCevir(metin: string): number | null {
  const d = Number(metin.trim().replace(',', '.'));
  return metin.trim() && Number.isFinite(d) ? d : null;
}

const TZ = 'Europe/Istanbul';

export function tarihSaat(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(yerelAd(dil), { timeZone: TZ, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function bugun(): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

export function gunOnce(gun: number): string {
  const d = new Date(`${bugun()}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - gun);
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// Sepet hesabı — sunucudaki `services/stok_pos.sepet_hesapla` ile aynı tam sayı aritmetiği
// (gösterim için; kayıt sunucuda yeniden hesaplanır ve `beklenen_toplam` ile karşılaştırılır).
// ---------------------------------------------------------------------------
export function yuvarla(pay: number, carpan: number, bolen: number): number {
  if (!bolen) return 0;
  const deger = pay * carpan;
  const isaret = deger < 0 !== bolen < 0 ? -1 : 1;
  const a = Math.abs(deger);
  const b = Math.abs(bolen);
  return isaret * Math.floor((2 * a + b) / (2 * b));
}

export function dagit(toplam: number, agirliklar: number[]): number[] {
  const n = agirliklar.length;
  const at = agirliklar.reduce((x, a) => x + Math.max(0, a), 0);
  if (!n || at <= 0 || !toplam) return agirliklar.map(() => 0);
  const paylar: number[] = [];
  const kalanlar: [number, number][] = [];
  agirliklar.forEach((a, i) => {
    const c = toplam * Math.max(0, a);
    paylar.push(Math.floor(c / at));
    kalanlar.push([c % at, -i]);
  });
  let eksik = toplam - paylar.reduce((x, p) => x + p, 0);
  kalanlar.sort((a, b) => (b[0] - a[0]) || (b[1] - a[1]));
  for (const [, ei] of kalanlar) {
    if (eksik <= 0) break;
    paylar[-ei] += 1;
    eksik -= 1;
  }
  return paylar;
}

export interface SepetToplami {
  ara_toplam: number;
  satir_indirim: number;
  toplam_indirim: number;
  toplam: number;
  kdv_dokumu: KdvSatiri[];
  satirlar: { brut: number; tutar: number }[];
}

export function sepetHesapla(kalemler: SepetKalemi[], toplamIndirim: number): SepetToplami {
  const ara = kalemler.map((k) => {
    const brut = yuvarla(k.birim_fiyat, Math.round(k.adet * 1000), 1000);
    return { k, brut, ind: Math.max(0, Math.min(k.indirim || 0, brut)) };
  });
  const netler = ara.map((a) => a.brut - a.ind);
  const net = netler.reduce((x, n) => x + n, 0);
  const ti = Math.max(0, Math.min(toplamIndirim || 0, net));
  const paylar = dagit(ti, netler);
  const satirlar = ara.map((a, i) => ({ brut: a.brut, tutar: netler[i] - paylar[i] }));
  const gruplar = new Map<number, number>();
  satirlar.forEach((s, i) => gruplar.set(ara[i].k.kdv_orani, (gruplar.get(ara[i].k.kdv_orani) || 0) + s.tutar));
  const kdv_dokumu = [...gruplar.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([oran, tutar]) => {
      const kdv = oran > 0 && tutar ? yuvarla(tutar, oran, 100 + oran) : 0;
      return { oran, tutar, matrah: tutar - kdv, kdv };
    });
  return {
    ara_toplam: ara.reduce((x, a) => x + a.brut, 0),
    satir_indirim: ara.reduce((x, a) => x + a.ind, 0),
    toplam_indirim: ti,
    toplam: net - ti,
    kdv_dokumu,
    satirlar,
  };
}

// ---------------------------------------------------------------------------
// Yerel sepet (ağ koparsa satış kaybolmasın): tarayıcıya özel kolaylık, okunamazsa yok sayılır.
// ---------------------------------------------------------------------------
export interface YerelSepet {
  kalemler: SepetKalemi[];
  toplamIndirim: number;
  istemciKimligi: string;
  musteriAd?: string;
  aliciId?: number | null;
}

const SEPET_ANAHTARI = 'mk_pos_sepet';

export function yerelSepetOku(hesap: string): YerelSepet | null {
  try {
    const ham = localStorage.getItem(`${SEPET_ANAHTARI}:${hesap}`);
    if (!ham) return null;
    const s = JSON.parse(ham) as YerelSepet;
    return Array.isArray(s?.kalemler) ? s : null;
  } catch {
    return null;
  }
}

export function yerelSepetYaz(hesap: string, s: YerelSepet | null): void {
  try {
    if (!s || !s.kalemler.length) localStorage.removeItem(`${SEPET_ANAHTARI}:${hesap}`);
    else localStorage.setItem(`${SEPET_ANAHTARI}:${hesap}`, JSON.stringify(s));
  } catch {
    /* depolama yok */
  }
}

/** Satışın istemci kimliği — UUID v4 (Faz 6Q; sunucu hesapta benzersiz tutar, tekrar gönderim tek kayıt). */
export function yeniKimlik(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    const d = new Uint8Array(16);
    crypto.getRandomValues(d);
    d[6] = (d[6] & 0x0f) | 0x40;
    d[8] = (d[8] & 0x3f) | 0x80;
    const h = Array.from(d, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  }
}
