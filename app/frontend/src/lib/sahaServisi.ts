import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 6S — Saha servisi: panel uçları ve küçük yardımcılar.
 *
 * Müşteri paneli `/api/v1/saha-servisim/...` (etkin hesap = servis firması; `X-MK-Hesap`),
 * ajans paneli `/api/v1/saha/yonetim/...?hesap=` (salt okunur destek görünümü). Bu dosya yalnız
 * sekme açıldığında (lazy) iniyor.
 */

export type SahaMod = 'musteri' | 'yonetici';
export type IsTuru = 'kurulum' | 'ariza' | 'bakim' | 'temizlik' | 'kesif';
export type Oncelik = 'dusuk' | 'normal' | 'yuksek' | 'acil';
export type Durum = 'yeni' | 'planlandi' | 'yolda' | 'iste' | 'tamamlandi' | 'iptal' | 'ertelendi';
export type MaddeTuru = 'evet_hayir' | 'metin' | 'sayi' | 'olcum' | 'foto';

export const IS_TURLERI: IsTuru[] = ['kurulum', 'ariza', 'bakim', 'temizlik', 'kesif'];
export const ONCELIKLER: Oncelik[] = ['dusuk', 'normal', 'yuksek', 'acil'];
export const DURUMLAR: Durum[] = ['yeni', 'planlandi', 'yolda', 'iste', 'tamamlandi', 'iptal', 'ertelendi'];
export const MADDE_TURLERI: MaddeTuru[] = ['evet_hayir', 'metin', 'sayi', 'olcum', 'foto'];
export const BIRIMLER = ['adet', 'm', 'm2', 'kg', 'lt', 'paket', 'saat', 'takim'];
export const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'];

export interface Teknisyen {
  id: number;
  eposta: string;
  ad: string;
  telefon: string | null;
  renk: string;
  aktif: boolean;
  sira: number;
  konum_rizasi: boolean;
  konum_rizasi_at: string | null;
  konum_rizasi_surumu: string | null;
  konum_rizasi_geri_at: string | null;
}

export interface Meta {
  hesap: string;
  yonetim: boolean;
  teknisyen: boolean;
  teknisyen_izni: boolean;
  salt_okunur: boolean;
  benim: Teknisyen | null;
  riza_surumu: string;
  konum_saklama_gun: number;
  teknisyen_siniri: number;
  aylik_is_emri_siniri: number;
  bu_ay_is_emri: number;
  gecisler: Record<Durum, Durum[]>;
  teknisyen_gecisleri: [Durum, Durum][];
  foto_siniri: number;
  ayarlar: { firma_adi: string | null; para_birimi: string; kdv_orani: number; imza_zorunlu: boolean };
}

export interface Lokasyon {
  id: number;
  musteri_id: number;
  ad: string;
  adres: string;
  ilce: string;
  il: string;
  posta_kodu: string;
  notlar: string;
  tam_adres: string;
  harita: string | null;
}

export interface Cihaz {
  id: number;
  musteri_id: number;
  lokasyon_id: number | null;
  tur: string;
  marka: string;
  model: string;
  seri_no: string;
  kurulum_tarihi: string | null;
  garanti_bitis: string | null;
  son_bakim: string | null;
  bakim_periyot_ay: number | null;
  bakim_vadesi: string | null;
  notlar: string;
  aktif: boolean;
  garantide: boolean;
}

export interface Musteri {
  id: number;
  tur: 'bireysel' | 'kurumsal';
  ad: string;
  firma: string | null;
  eposta: string | null;
  telefon: string | null;
  vergi_no: string | null;
  notlar: string;
  dil: string;
  anonim: boolean;
  son_is_at: string | null;
  lokasyonlar?: Lokasyon[];
  cihazlar?: Cihaz[];
  isler?: IsOzeti[];
}

export interface Madde {
  id: string;
  metin: string;
  tur: MaddeTuru;
  zorunlu: boolean;
  birim?: string;
}

export interface Sablon {
  id: number;
  ad: string;
  is_turu: IsTuru | null;
  maddeler: Madde[];
  aktif: boolean;
  hazir: string | null;
}

export interface Malzeme {
  id: number;
  ad: string;
  kod: string;
  birim: string;
  birim_fiyat: number;
  stok: number | null;
  kritik_stok: number | null;
  aktif: boolean;
  kritik: boolean;
}

export interface IsOzeti {
  id: number;
  no: string;
  tur: IsTuru;
  oncelik: Oncelik;
  durum: Durum;
  baslik: string;
  musteri_id: number;
  musteri_ad: string;
  musteri_telefon: string | null;
  lokasyon_id: number | null;
  adres: string | null;
  plan_bas: string | null;
  plan_bit: string | null;
  tahmini_dk: number;
  teknisyenler: { id: number; ad: string; renk: string }[];
  basla_at: string | null;
  bitir_at: string | null;
  memnuniyet_puan: number | null;
  imzali: boolean;
  randevu_id: number | null;
  created_at: string | null;
  cakisan?: number[];
}

export interface Fotograf {
  id: number;
  tur: 'once' | 'sonra' | 'madde';
  madde_id: string | null;
  url: string;
  kucuk_url: string;
  genislik: number;
  yukseklik: number;
}

export interface Kullanim {
  id: number;
  malzeme_id: number | null;
  ad: string;
  birim: string;
  miktar: number;
  birim_fiyat: number;
  tutar: number;
}

export interface IsAyrintisi extends IsOzeti {
  aciklama: string;
  musteri: Musteri | null;
  lokasyon: Lokasyon | null;
  cihazlar: Cihaz[];
  sablon_id: number | null;
  kontrol_listesi: Madde[];
  kontrol_yanitlari: Record<string, string | number | boolean>;
  teknisyen_notu: string;
  iscilik_dk: number | null;
  iscilik_ucreti: number;
  takip_gerekli: boolean;
  ertele_sayisi: number;
  zaman: Record<'planlandi' | 'yolda' | 'basla' | 'bitir' | 'iptal' | 'ertele', string | null>;
  fotograflar: Fotograf[];
  foto_siniri: number;
  malzemeler: Kullanim[];
  gecmis: { eski: Durum | null; yeni: Durum; kisi: string | null; neden: string | null; konum_alindi: boolean; zaman: string }[];
  imza: { ad: string; at: string; url: string } | null;
  memnuniyet: { puan: number; yorum: string | null; at: string } | null;
  konum_alindi: { basla: boolean; bitir: boolean; indirgendi_at: string | null };
  konum?: { basla: { enlem: number; boylam: number; dogruluk: number | null } | null; bitir: { enlem: number; boylam: number; dogruluk: number | null } | null };
  musteri_baglantisi?: string;
  benim_isim: boolean;
  anonim: boolean;
  cakismalar?: { is_emri_id: number; no: string; baslik: string; teknisyen_id: number }[];
  konum_kaydedildi?: boolean;
}

export interface Pano {
  bas: string;
  bit: string;
  gun: string;
  gorunum: 'gun' | 'hafta';
  teknisyenler: Teknisyen[];
  isler: IsOzeti[];
  kuyruk: IsOzeti[];
}

export interface RaporOzeti {
  tamamlanan: number;
  ortalama_sure_dk: number | null;
  ilk_seferde_oran: number | null;
  memnuniyet_ortalama: number | null;
  puan_sayisi: number;
}

export interface Rapor {
  bas: string;
  bit: string;
  toplam: RaporOzeti;
  teknisyenler: (RaporOzeti & { teknisyen_id: number; ad: string; renk: string; aktif: boolean })[];
  acik: Record<string, number>;
}

export interface BakimSatiri {
  cihaz_id: number;
  musteri_id: number;
  musteri_ad: string | null;
  tur: string;
  marka: string | null;
  model: string | null;
  seri_no: string | null;
  son_bakim: string | null;
  vade: string;
  gecikme_gun: number;
  acik_is_emri: { id: number; no: string } | null;
}

export interface Ayarlar {
  firma_adi: string | null;
  telefon: string | null;
  eposta: string | null;
  adres: string | null;
  vergi_no: string | null;
  varsayilan_dil: string;
  para_birimi: string;
  kdv_orani: number;
  saklama_ay: number;
  imza_zorunlu: boolean;
  bildirim_planlandi: boolean;
  bildirim_yolda: boolean;
  bildirim_tamamlandi: boolean;
  memnuniyet_acik: boolean;
  yorum_sayfasi_id: number | null;
  randevu_kancasi: boolean;
  randevu_is_turu: IsTuru;
  bakim_on_gun: number;
  yorum_sayfalari?: { id: number; ad: string }[];
  /** Yalnız okumada: dış bağımlılıklar (e-posta kanalı, randevu ve yorum sayfası modülleri). */
  eposta_kanali?: boolean;
  randevu_modulu?: boolean;
  yorum_modulu?: boolean;
}

export interface Riza {
  kayitli: boolean;
  gecerli: boolean;
  surum: string;
  verildi_at?: string | null;
  geri_alindi_at?: string | null;
}

export class SahaHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): SahaHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new SahaHatasi(durum, kod, ek);
  }
  if (durum === 429) return new SahaHatasi(durum, 'cok_hizli');
  if (durum === 404) return new SahaHatasi(durum, 'bulunamadi');
  if (durum === 403) return new SahaHatasi(durum, 'yetki_yok');
  return new SahaHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new SahaHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = (await yanit.json().catch(() => null)) as { detail?: unknown } | null;
    throw hataCoz(yanit.status, govde?.detail);
  }
  return yanit;
}

/** Göreli görsel adresi (`/api/v1/saha/gorsel/...`) → API kökenine göre mutlak. */
export function gorselAdresi(yol: string): string {
  return yol.startsWith('/') ? `${getAPIBaseURL()}${yol}` : yol;
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

export function sahaApi(mod: SahaMod, hesap?: string) {
  const T = mod === 'yonetici' ? '/api/v1/saha/yonetim' : '/api/v1/saha-servisim';
  /** Yönetici uçlarında her istek `?hesap=` taşıyor. */
  const u = (yol: string, q?: Record<string, string | number | undefined | null>) => {
    const p = new URLSearchParams();
    if (mod === 'yonetici' && hesap) p.set('hesap', hesap);
    for (const [k, v] of Object.entries(q || {})) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
    const s = p.toString();
    return `${T}${yol}${s ? `?${s}` : ''}`;
  };
  return {
    mod,
    hesaplar: () => istek<{ items: { hesap_email: string; firma_adi: string | null; is_emri: number }[] }>('GET', '/api/v1/saha/yonetim/hesaplar'),
    meta: () => istek<Meta>('GET', u('/meta')),
    ayarlar: () => istek<Ayarlar>('GET', u('/ayarlar')),
    ayarlarKaydet: (g: Partial<Ayarlar>) => istek<Ayarlar>('PUT', u('/ayarlar'), g),
    teknisyenler: () =>
      istek<{ items: Teknisyen[]; adaylar: { eposta: string; sahip: boolean; durum?: string; teknisyen_izni?: boolean }[]; sinir: number }>(
        'GET',
        u('/teknisyenler')
      ),
    teknisyenEkle: (g: { eposta: string; ad?: string; telefon?: string; renk?: string }) => istek<Teknisyen>('POST', u('/teknisyenler'), g),
    teknisyenGuncelle: (id: number, g: Partial<Teknisyen>) => istek<Teknisyen>('PUT', u(`/teknisyenler/${id}`), g),
    teknisyenSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/teknisyenler/${id}`)),
    rizam: () => istek<Riza>('GET', u('/rizam')),
    rizaVer: (surum: string) => istek<Riza>('POST', u('/rizam'), { surum, onay: true }),
    rizaGeriAl: () => istek<Riza>('DELETE', u('/rizam')),
    musteriler: (ara?: string) => istek<{ items: Musteri[] }>('GET', u('/musteriler', { ara })),
    musteri: (id: number) => istek<Musteri>('GET', u(`/musteriler/${id}`)),
    musteriEkle: (g: Record<string, unknown>) => istek<Musteri>('POST', u('/musteriler'), g),
    musteriGuncelle: (id: number, g: Record<string, unknown>) => istek<Musteri>('PUT', u(`/musteriler/${id}`), g),
    musteriSil: (id: number) => istek<{ ok: boolean; anonimlesti: boolean }>('DELETE', u(`/musteriler/${id}`)),
    lokasyonEkle: (mid: number, g: Record<string, unknown>) => istek<Lokasyon>('POST', u(`/musteriler/${mid}/lokasyonlar`), g),
    lokasyonGuncelle: (id: number, g: Record<string, unknown>) => istek<Lokasyon>('PUT', u(`/lokasyonlar/${id}`), g),
    lokasyonSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/lokasyonlar/${id}`)),
    cihazEkle: (mid: number, g: Record<string, unknown>) => istek<Cihaz>('POST', u(`/musteriler/${mid}/cihazlar`), g),
    cihazGuncelle: (id: number, g: Record<string, unknown>) => istek<Cihaz>('PUT', u(`/cihazlar/${id}`), g),
    cihazSil: (id: number) => istek<{ ok: boolean; pasif: boolean }>('DELETE', u(`/cihazlar/${id}`)),
    cihazGecmisi: (id: number) => istek<{ cihaz: Cihaz; isler: IsOzeti[] }>('GET', u(`/cihazlar/${id}/gecmis`)),
    bakimIsEmri: (id: number, g: Record<string, unknown> = {}) => istek<IsAyrintisi>('POST', u(`/cihazlar/${id}/bakim-is-emri`), g),
    sablonlar: () => istek<{ items: Sablon[] }>('GET', u('/sablonlar')),
    sablonEkle: (g: Partial<Sablon>) => istek<Sablon>('POST', u('/sablonlar'), g),
    sablonGuncelle: (id: number, g: Partial<Sablon>) => istek<Sablon>('PUT', u(`/sablonlar/${id}`), g),
    sablonSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/sablonlar/${id}`)),
    malzemeler: () => istek<{ items: Malzeme[] }>('GET', u('/malzemeler')),
    malzemeEkle: (g: Record<string, unknown>) => istek<Malzeme>('POST', u('/malzemeler'), g),
    malzemeGuncelle: (id: number, g: Record<string, unknown>) => istek<Malzeme>('PUT', u(`/malzemeler/${id}`), g),
    malzemeSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/malzemeler/${id}`)),
    isler: (q: { durum?: string; ara?: string; teknisyen?: number; musteri?: number } = {}) =>
      istek<{ items: IsOzeti[] }>('GET', u('/is-emirleri', q as Record<string, string | number | undefined>)),
    is: (id: number) => istek<IsAyrintisi>('GET', u(`/is-emirleri/${id}`)),
    isEkle: (g: Record<string, unknown>) => istek<IsAyrintisi>('POST', u('/is-emirleri'), g),
    isGuncelle: (id: number, g: Record<string, unknown>) => istek<IsAyrintisi>('PUT', u(`/is-emirleri/${id}`), g),
    plan: (id: number, g: { teknisyen_id?: number | null; eski_teknisyen_id?: number | null; plan_bas?: string | null }) =>
      istek<IsAyrintisi>('PUT', u(`/is-emirleri/${id}/plan`), g),
    isSil: (id: number) => istek<{ ok: boolean }>('DELETE', u(`/is-emirleri/${id}`)),
    durum: (id: number, g: { durum: Durum; neden?: string; konum?: { enlem: number; boylam: number; dogruluk?: number } }) =>
      istek<IsAyrintisi>('POST', u(`/is-emirleri/${id}/durum`), g),
    kontrol: (id: number, yanitlar: Record<string, unknown>) =>
      istek<{ kontrol_yanitlari: Record<string, string | number | boolean> }>('PUT', u(`/is-emirleri/${id}/kontrol`), { yanitlar }),
    saha: (id: number, g: { teknisyen_notu?: string; iscilik_dk?: number | null; takip_gerekli?: boolean }) =>
      istek<{ teknisyen_notu: string; iscilik_dk: number | null; takip_gerekli: boolean }>('PUT', u(`/is-emirleri/${id}/saha`), g),
    async fotoYukle(id: number, dosya: File, tur: Fotograf['tur'], madde?: string): Promise<Fotograf> {
      const form = new FormData();
      form.append('dosya', dosya);
      form.append('tur', tur);
      if (madde) form.append('madde_id', madde);
      const y = await hamIstek(u(`/is-emirleri/${id}/fotograflar`), { method: 'POST', body: form });
      return (await y.json()) as Fotograf;
    },
    fotoSil: (id: number, fid: number) => istek<{ ok: boolean }>('DELETE', u(`/is-emirleri/${id}/fotograflar/${fid}`)),
    kullanimEkle: (id: number, g: Record<string, unknown>) => istek<Kullanim>('POST', u(`/is-emirleri/${id}/malzemeler`), g),
    kullanimSil: (id: number, kid: number) => istek<{ ok: boolean }>('DELETE', u(`/is-emirleri/${id}/malzemeler/${kid}`)),
    imza: (id: number, ad: string, png: string) => istek<{ imza: IsAyrintisi['imza'] }>('POST', u(`/is-emirleri/${id}/imza`), { ad, png }),
    async pdf(id: number, dil?: string): Promise<Blob> {
      const y = await hamIstek(u(`/is-emirleri/${id}/pdf`, { dil }), { method: 'GET' });
      return y.blob();
    },
    musteriBaglantisi: (id: number) => istek<{ adres: string }>('POST', u(`/is-emirleri/${id}/musteri-baglantisi`)),
    pano: (gun: string, gorunum: 'gun' | 'hafta') => istek<Pano>('GET', u('/pano', { gun, gorunum })),
    islerim: (gun?: string) =>
      istek<{ kayitli: boolean; teknisyen?: Teknisyen; gun?: string; bugun: IsOzeti[]; diger: IsOzeti[] }>('GET', u('/islerim', { gun })),
    raporlar: (bas: string, bit: string) => istek<Rapor>('GET', u('/raporlar', { bas, bit })),
    bakim: (gun = 30) => istek<{ items: BakimSatiri[] }>('GET', u('/bakim', { gun })),
  };
}

export type SahaApi = ReturnType<typeof sahaApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof SahaHatasi) {
    return t(`sahaServisi.hata.${e.kod}`, { ...e.ek, defaultValue: t('sahaServisi.hata.genel') }) as string;
  }
  return t('sahaServisi.hata.genel');
}

// ---------------------------------------------------------------------------
// Biçim
// ---------------------------------------------------------------------------
const TZ = 'Europe/Istanbul';

export function tarihSaat(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { timeZone: TZ, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function saatYaz(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { timeZone: TZ, hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function gunYaz(gun: string, dil: string, uzun = false): string {
  try {
    const [y, a, g] = gun.split('-').map(Number);
    return new Intl.DateTimeFormat(dil, { timeZone: 'UTC', weekday: uzun ? 'long' : 'short', day: 'numeric', month: 'short' }).format(
      new Date(Date.UTC(y, a - 1, g))
    );
  } catch {
    return gun;
  }
}

export function paraYaz(kurus: number, birim: string, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: birim || 'TRY' }).format((kurus || 0) / 100);
  } catch {
    return `${((kurus || 0) / 100).toFixed(2)} ${birim}`;
  }
}

/** İstanbul saatiyle bugünün tarihi (YYYY-AA-GG). */
export function bugunIso(): string {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

export function gunEkle(gun: string, n: number): string {
  const [y, a, g] = gun.split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1, g + n));
  return d.toISOString().slice(0, 10);
}

/** İstanbul (UTC+3, yaz saati yok) yerel tarih + saat → UTC ISO. */
export function yerelIso(gun: string, saat: string): string {
  const [y, a, g] = gun.split('-').map(Number);
  const [s, d] = saat.split(':').map(Number);
  return new Date(Date.UTC(y, a - 1, g, s - 3, d)).toISOString().replace('.000Z', 'Z');
}

/** UTC ISO → İstanbul `YYYY-AA-GGTSS:DD` (datetime-local girdisi için). */
export function yerelGirdi(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(new Date(iso).getTime() + 3 * 3600 * 1000);
  return d.toISOString().slice(0, 16);
}

export function girdidenIso(deger: string): string | null {
  if (!deger) return null;
  const [gun, saat] = deger.split('T');
  return gun && saat ? yerelIso(gun, saat.slice(0, 5)) : null;
}

/** UTC ISO → İstanbul saat dakika (gün başından). */
export function gunDakikasi(iso: string): number {
  const d = new Date(new Date(iso).getTime() + 3 * 3600 * 1000);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

export function haritaAdresi(adres: string): string {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(adres)}`;
}

export function yolTarifi(adres: string): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(adres)}`;
}

// ---------------------------------------------------------------------------
// Zayıf bağlantı: form taslağı tarayıcıda (localStorage), bağlantı gelince gönderilir
// ---------------------------------------------------------------------------
export interface Taslak {
  yanitlar?: Record<string, unknown>;
  not?: string;
  iscilik_dk?: number | null;
  takip_gerekli?: boolean;
  /** Sunucuya henüz gitmemiş alanlar var. */
  bekliyor?: boolean;
  zaman?: number;
}

const taslakAnahtari = (hesap: string, id: number) => `mk_saha_taslak_${hesap}_${id}`;

export function taslakOku(hesap: string, id: number): Taslak | null {
  try {
    const ham = localStorage.getItem(taslakAnahtari(hesap, id));
    return ham ? (JSON.parse(ham) as Taslak) : null;
  } catch {
    return null;
  }
}

export function taslakYaz(hesap: string, id: number, t: Taslak): void {
  try {
    localStorage.setItem(taslakAnahtari(hesap, id), JSON.stringify({ ...t, zaman: Date.now() }));
  } catch {
    /* depolama dolu ya da kapalı: taslak yalnız bellekte */
  }
}

export function taslakSil(hesap: string, id: number): void {
  try {
    localStorage.removeItem(taslakAnahtari(hesap, id));
  } catch {
    /* yoksay */
  }
}

/** Tek seferlik konum (yalnız başla/bitir dokunuşunda). İzin yok / zaman aşımı → null. */
export function tekSeferlikKonum(): Promise<{ enlem: number; boylam: number; dogruluk?: number } | null> {
  return new Promise((coz) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      coz(null);
      return;
    }
    try {
      navigator.geolocation.getCurrentPosition(
        (p) => coz({ enlem: p.coords.latitude, boylam: p.coords.longitude, dogruluk: Math.round(p.coords.accuracy * 10) / 10 }),
        () => coz(null),
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
      );
    } catch {
      coz(null);
    }
  });
}
