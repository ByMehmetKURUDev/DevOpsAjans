import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';
import type { OkutmaYaniti } from '@/lib/etkinlikOrtak';

/**
 * Faz 6K — Eğitim modülü: panel uçları.
 *
 * Yönetici `/api/v1/egitim/yonetim/...`, müşteri `/api/v1/egitimim/...` (etkin hesap `X-MK-Hesap`
 * başlığıyla). İki panel aynı bileşeni kullanıyor; yalnız taban yol değişiyor. Bu dosya yalnız sekme
 * açıldığında (lazy) iniyor.
 */

export type EgitimMod = 'yonetici' | 'musteri';
export type KursDurumu = 'taslak' | 'yayinda' | 'tamamlandi' | 'arsiv';
export type OgrenciDurumu = 'aktif' | 'bekleme' | 'ayrildi';
export type YoklamaDurumu = 'var' | 'gec' | 'yok' | 'izinli';
export type SoruTuru = 'coktan' | 'dogru_yanlis' | 'kisa';

export interface Egitmen {
  ad: string;
  eposta: string;
}

export interface Kurs {
  id: number;
  hesap_email: string | null;
  ajans: boolean;
  slug: string;
  adres_url: string;
  ad: string;
  ozet: string;
  aciklama: string;
  renk: string;
  egitmenler: Egitmen[];
  bicim: 'yuz_yuze' | 'online' | 'karma';
  mekan: string;
  adres: string;
  online_baglanti: string;
  saat_dilimi: string;
  baslangic_tarihi: string | null;
  bitis_tarihi: string | null;
  kapasite: number | null;
  fiyat_metni: string;
  durum: KursDurumu;
  kayit_acik: boolean;
  bekleme_listesi: boolean;
  hedef_kitle: 'yetiskin' | 'cocuk' | 'karma';
  telefon: 'gizli' | 'istege_bagli' | 'zorunlu';
  dil: string;
  kvkk_metni: string;
  arama_motoru: boolean;
  listede_goster: boolean;
  devamsizlik_esik: number;
  hatirlatma_saat: number;
  sertifika_aktif: boolean;
  otomatik_sertifika: boolean;
  kosul_ilerleme: number;
  kosul_quiz: number;
  kosul_yoklama: number;
  sertifika_sablon: 'klasik' | 'modern';
  sertifika_saat: number | null;
  saklama_gun: number;
  ogrenci?: number;
  bekleme?: number;
  sonraki_ders?: string | null;
  yonetim?: boolean;
}

export interface Meta {
  yonetici: boolean;
  yonetim: boolean;
  egitmen: boolean;
  kisi: string;
  kurs_siniri: number | null;
  kurs_sayisi: number | null;
  ogrenci_siniri: number | null;
  ogrenci_sayisi: number | null;
  ai: { hazir: boolean; hak: number | null; kullanilan: number; kredi_ile_asim: boolean; uretim_kredisi: number } | null;
  adres_tabani: string;
  varsayilan_saat_dilimi: string;
  en_cok_csv: number;
  saklama: { en_az: number; en_cok: number; varsayilan: number };
}

export interface Oturum {
  id: number;
  kurs_id: number;
  baslangic: string;
  bitis: string;
  konu: string;
  durum: 'planli' | 'iptal';
  yoklama_acik: boolean;
  katilan?: number;
}

export interface Kosul {
  deger: number | null;
  esik: number;
  tamam: boolean;
}

export interface Istatistik {
  ilerleme: number;
  tamamlanan_ders: number;
  ders_sayisi: number;
  quiz_ortalama: number | null;
  yoklama: number | null;
  katildi: number;
  oturum: number;
  devamsizlik: number;
  kosullar: { ilerleme: Kosul; quiz: Kosul; yoklama: Kosul };
  uygun: boolean;
  sertifika: string | null;
}

export interface Ogrenci {
  id: number;
  kod: string;
  ad: string;
  durum: OgrenciDurumu;
  cocuk: boolean;
  anonim: boolean;
  created_at: string;
  eposta?: string;
  telefon?: string;
  veli_ad?: string;
  veli_telefon?: string;
  veli_eposta?: string;
  kaynak?: string;
  notlar?: string;
  pazarlama_izni?: boolean;
  portal_son_at?: string | null;
  istatistik?: Istatistik;
}

export interface Dosya {
  id: number;
  ad: string;
  tur: string;
  boyut: number;
}

export interface Ders {
  id: number;
  kurs_id: number;
  bolum: string;
  sira: number;
  baslik: string;
  icerik: string;
  video_url: string;
  video: { saglayici: 'youtube' | 'vimeo' | 'baglanti'; kimlik: string | null; adres: string } | null;
  sure_dk: number | null;
  yayinda: boolean;
  dosyalar: Dosya[];
}

export interface Soru {
  id?: string;
  tur: SoruTuru;
  metin: string;
  secenekler?: string[];
  dogru: number | boolean | string[];
  puan?: number;
}

export interface Quiz {
  id: number;
  kurs_id: number;
  ders_id: number | null;
  tur: 'quiz' | 'odev';
  baslik: string;
  aciklama: string;
  sorular: Soru[];
  soru_sayisi: number;
  sure_dk: number | null;
  gecme_puani: number;
  deneme_hakki: number;
  son_tarih: string | null;
  yayinda: boolean;
  ai_uretildi: boolean;
  notlanmayan?: number;
}

export interface Sertifika {
  id: number;
  kod: string;
  kod_yazi: string;
  ogrenci_id: number;
  ad: string | null;
  ad_maskeli: string | null;
  verilme_at: string;
  iptal_at: string | null;
  kaynak: string;
  dogrulama_adresi: string;
}

export interface HesapAyari {
  kapsam: string;
  kurum_adi: string;
  imza_adi: string;
  imza_unvan: string;
  liste_slug: string;
  liste_baslik: string;
  liste_aciklama: string;
  liste_acik: boolean;
  liste_adresi: string | null;
}

export interface YoklamaListesi {
  oturum: Oturum;
  yoklama: { adres: string; kod: string; acik: boolean; pencere_bas: string; pencere_bit: string };
  kurs: { id: number; ad: string; saat_dilimi: string };
  items: { id: number; ad: string; kod: string; durum: YoklamaDurumu | null; kaynak: string | null; zaman: string | null }[];
}

export class EgitimUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): EgitimUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new EgitimUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new EgitimUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new EgitimUcHatasi(durum, 'bulunamadi');
  return new EgitimUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new EgitimUcHatasi(0, 'ag');
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

export function egitimApi(mod: EgitimMod) {
  const T = mod === 'yonetici' ? '/api/v1/egitim/yonetim' : '/api/v1/egitimim';
  const K = (id: number) => `${T}/${id}`;
  return {
    taban: T,
    mod,
    meta: () => istek<Meta>('GET', `${T}/meta`),
    ayarlar: () => istek<HesapAyari>('GET', `${T}/ayarlar`),
    ayarlarYaz: (g: Partial<HesapAyari>) => istek<HesapAyari>('PUT', `${T}/ayarlar`, g),
    liste: (hesap?: string) => istek<{ items: Kurs[]; toplam: number }>('GET', `${T}${hesap ? `?hesap=${encodeURIComponent(hesap)}` : ''}`),
    olustur: (g: Record<string, unknown>) => istek<Kurs>('POST', T, g),
    getir: (id: number) => istek<Kurs>('GET', K(id)),
    guncelle: (id: number, g: Record<string, unknown>) => istek<Kurs>('PUT', K(id), g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', K(id)),
    async qrBlob(id: number, bicim: 'png' | 'svg'): Promise<Blob> {
      return (await hamIstek(`${K(id)}/qr?bicim=${bicim}`, { method: 'GET' })).blob();
    },
    async takvimBlob(id: number): Promise<Blob> {
      return (await hamIstek(`${K(id)}/takvim.ics`, { method: 'GET' })).blob();
    },
    oturumlar: (id: number) => istek<{ items: Oturum[]; aktif_ogrenci: number; saat_dilimi: string }>('GET', `${K(id)}/oturumlar`),
    oturumEkle: (id: number, g: { baslangic: string; bitis: string; konu?: string }) => istek<Oturum>('POST', `${K(id)}/oturumlar`, g),
    oturumUret: (id: number, g: Record<string, unknown>) => istek<{ eklenen: number; atlanan: number }>('POST', `${K(id)}/oturumlar/uret`, g),
    oturumGuncelle: (id: number, oid: number, g: Record<string, unknown>) => istek<Oturum>('PUT', `${K(id)}/oturumlar/${oid}`, g),
    oturumSil: (id: number, oid: number) => istek<{ ok: boolean }>('DELETE', `${K(id)}/oturumlar/${oid}`),
    yoklama: (id: number, oid: number) => istek<YoklamaListesi>('GET', `${K(id)}/oturumlar/${oid}/yoklama`),
    yoklamaDuzelt: (id: number, oid: number, ogid: number, durum: YoklamaDurumu | null) =>
      istek<{ ok: boolean }>('PUT', `${K(id)}/oturumlar/${oid}/yoklama/${ogid}`, { durum }),
    yoklamaKapat: (id: number, oid: number) => istek<{ ok: boolean; yok: number }>('POST', `${K(id)}/oturumlar/${oid}/yoklama-kapat`),
    async oturumQr(id: number, oid: number): Promise<Blob> {
      return (await hamIstek(`${K(id)}/oturumlar/${oid}/qr?bicim=svg`, { method: 'GET' })).blob();
    },
    qrYenile: (id: number, oid: number) => istek<YoklamaListesi['yoklama']>('POST', `${K(id)}/oturumlar/${oid}/qr-yenile`),
    okut: (id: number, oid: number, kod: string) => istek<OkutmaYaniti>('POST', `${K(id)}/oturumlar/${oid}/okut`, { kod }),
    ogrenciler: (id: number, durum?: string) =>
      istek<{ items: Ogrenci[]; toplam: number; kapasite: number | null }>('GET', `${K(id)}/ogrenciler${durum ? `?durum=${durum}` : ''}`),
    ogrenciEkle: (id: number, g: Record<string, unknown>) => istek<Ogrenci>('POST', `${K(id)}/ogrenciler`, g),
    ogrenciCsv: (id: number, csv: string, bildir: boolean) =>
      istek<{ aktif: number; bekleme: number; atlanan: number; hatalar: { satir: number; kod: string; alan: string | null }[]; hata_sayisi: number }>(
        'POST',
        `${K(id)}/ogrenciler/csv`,
        { csv, bildir }
      ),
    async ogrenciCsvBlob(id: number): Promise<Blob> {
      return (await hamIstek(`${K(id)}/ogrenciler.csv`, { method: 'GET' })).blob();
    },
    ogrenciGuncelle: (id: number, ogid: number, g: Record<string, unknown>) => istek<Ogrenci>('PUT', `${K(id)}/ogrenciler/${ogid}`, g),
    ogrenciSil: (id: number, ogid: number) => istek<{ ok: boolean }>('DELETE', `${K(id)}/ogrenciler/${ogid}`),
    ogrenciBaglantisi: (id: number, ogid: number, g: { yenile?: boolean; gonder?: boolean }) =>
      istek<{ adres: string; surum: number; gonderildi: boolean }>('POST', `${K(id)}/ogrenciler/${ogid}/baglanti`, g),
    ilerleme: (id: number) =>
      istek<{ items: ({ id: number; ad: string; kod: string } & Istatistik)[]; kosullar: { ilerleme: number; quiz: number; yoklama: number } }>(
        'GET',
        `${K(id)}/ilerleme`
      ),
    dersler: (id: number) => istek<{ items: Ders[] }>('GET', `${K(id)}/dersler`),
    dersEkle: (id: number, g: Partial<Ders>) => istek<Ders>('POST', `${K(id)}/dersler`, g),
    dersGuncelle: (id: number, did: number, g: Partial<Ders>) => istek<Ders>('PUT', `${K(id)}/dersler/${did}`, g),
    dersSil: (id: number, did: number) => istek<{ ok: boolean }>('DELETE', `${K(id)}/dersler/${did}`),
    dersSirasi: (id: number, sira: number[]) => istek<{ ok: boolean }>('PUT', `${K(id)}/dersler-sira`, { sira }),
    async dosyaYukle(id: number, did: number, dosya: File): Promise<Dosya> {
      const form = new FormData();
      form.append('dosya', dosya);
      return (await (await hamIstek(`${K(id)}/dersler/${did}/dosyalar`, { method: 'POST', body: form })).json()) as Dosya;
    },
    async dosyaBlob(id: number, fid: number): Promise<Blob> {
      return (await hamIstek(`${K(id)}/dosyalar/${fid}`, { method: 'GET' })).blob();
    },
    dosyaSil: (id: number, fid: number) => istek<{ ok: boolean }>('DELETE', `${K(id)}/dosyalar/${fid}`),
    quizler: (id: number) => istek<{ items: Quiz[] }>('GET', `${K(id)}/quizler`),
    quizEkle: (id: number, g: Record<string, unknown>) => istek<Quiz>('POST', `${K(id)}/quizler`, g),
    quizGuncelle: (id: number, qid: number, g: Record<string, unknown>) => istek<Quiz>('PUT', `${K(id)}/quizler/${qid}`, g),
    quizSil: (id: number, qid: number) => istek<{ ok: boolean }>('DELETE', `${K(id)}/quizler/${qid}`),
    aiSoru: (id: number, g: { ders_id: number; sayi: number; turler: SoruTuru[] }) =>
      istek<{ sorular: Soru[]; ai: NonNullable<Meta['ai']> }>('POST', `${K(id)}/quizler/ai`, g),
    sonuclar: (id: number, qid: number) => istek<{ tur: 'quiz' | 'odev'; items: Record<string, unknown>[] }>('GET', `${K(id)}/quizler/${qid}/sonuclar`),
    notla: (id: number, tid: number, g: { puan: number | null; geri_bildirim: string; bildir?: boolean }) =>
      istek<{ ok: boolean }>('PUT', `${K(id)}/teslimler/${tid}`, g),
    sertifikalar: (id: number) => istek<{ items: Sertifika[] }>('GET', `${K(id)}/sertifikalar`),
    sertifikaVer: (id: number, ogrenci_id: number, zorla = false) =>
      istek<Sertifika & { yeni: boolean }>('POST', `${K(id)}/sertifikalar`, { ogrenci_id, zorla }),
    sertifikaToplu: (id: number) => istek<{ verilen: number; uygun_olmayan: number }>('POST', `${K(id)}/sertifikalar/toplu`, {}),
    sertifikaIptal: (id: number, sid: number) => istek<{ ok: boolean }>('DELETE', `${K(id)}/sertifikalar/${sid}`),
    async sertifikaPdf(id: number, sid: number): Promise<Blob> {
      return (await hamIstek(`${K(id)}/sertifikalar/${sid}/pdf`, { method: 'GET' })).blob();
    },
    duyurular: (id: number) => istek<{ items: { id: number; konu: string; metin: string; alici: number; created_at: string }[] }>('GET', `${K(id)}/duyurular`),
    duyuru: (id: number, g: { konu: string; metin: string }) => istek<{ ok: boolean; alici: number }>('POST', `${K(id)}/duyuru`, g),
  };
}

export type EgitimApi = ReturnType<typeof egitimApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof EgitimUcHatasi) {
    return t(`egitim.hata.${e.kod}`, { ...e.ek, defaultValue: t('egitim.hata.genel') }) as string;
  }
  return t('egitim.hata.genel');
}

/** `datetime-local` değeri ↔ ISO (kursun saat diliminde). */
export function yerelGirdi(iso: string | null | undefined, tz: string): string {
  if (!iso) return '';
  try {
    const p = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(iso));
    const v = (x: string) => p.find((y) => y.type === x)?.value || '00';
    return `${v('year')}-${v('month')}-${v('day')}T${v('hour')}:${v('minute')}`;
  } catch {
    return iso.slice(0, 16);
  }
}

export function yerelIso(deger: string, tz: string): string | null {
  if (!deger) return null;
  const m = deger.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return null;
  const hedef = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  let an = hedef;
  for (let i = 0; i < 2; i++) {
    const yerel = yerelGirdi(new Date(an).toISOString(), tz);
    const y = yerel.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!y) break;
    const fark = Date.UTC(+y[1], +y[2] - 1, +y[3], +y[4], +y[5]) - hedef;
    an -= fark;
  }
  return new Date(an).toISOString().replace('.000Z', 'Z');
}

/** Gün başı (kursun saat diliminde) "YYYY-MM-DD". */
export function yerelGun(iso: string, tz: string): string {
  return yerelGirdi(iso, tz).slice(0, 10);
}

export function tarihSaat(iso: string | null | undefined, tz: string, dil: string, secenek: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(dil, { ...secenek, timeZone: tz }).format(new Date(iso));
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}

export function gunYaz(gun: string | null | undefined, dil: string): string {
  if (!gun) return '';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${gun}T00:00:00Z`));
  } catch {
    return gun;
  }
}
