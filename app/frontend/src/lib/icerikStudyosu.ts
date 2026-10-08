import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import type { KanalOzeti, Olcum } from '@/lib/icerikOnay';
import { client } from '@/lib/sdkClient';

/**
 * Faz 5I — İçerik stüdyosu: panel uçları ve tipler.
 *
 * Yönetici `/api/v1/icerik-studyosu/yonetim/...` (seçili hesap `?hesap=` — boş = ajansın kendi
 * içeriği), müşteri `/api/v1/icerik-studyom/...` (etkin hesap `X-MK-Hesap` başlığıyla). İki panel
 * aynı bileşeni kullanıyor. Kanal/alan sınırları sunucudan (`/meta` › `sinirlar`) — kodda tek yer.
 */

export type StudyoMod = 'yonetici' | 'musteri';
export type Durum = 'taslak' | 'incelemede' | 'musteri_onayi' | 'onaylandi' | 'yayinlandi' | 'reddedildi';
export type InceAyar = 'kisalt' | 'samimi' | 'emoji_ekle' | 'emoji_cikar' | 'cevir' | 'uyarla';
export type Politika = 'yok' | 'az' | 'serbest';
export type { KanalOzeti, Olcum };

export interface Uyari {
  tur: string;
  eslesen: string[];
}

export interface SablonGirdisi {
  anahtar: string;
  tur: 'metin' | 'uzun';
  zorunlu: boolean;
  etiket?: string;
}
export interface SablonCiktisi {
  anahtar: string;
  tur: 'metin' | 'liste' | 'sss';
  adet: [number, number] | null;
  sinir: number | null;
}
export interface Sablon {
  kod: string;
  hazir: boolean;
  id?: number;
  ad?: string;
  aciklama?: string;
  kanal: string | null;
  kanallar: string[];
  girdiler: SablonGirdisi[];
  ciktilar: SablonCiktisi[];
  uzman: string | null;
  istem?: string;
}

export interface Kullanim {
  ay: { uretim: number; kredi: number; token_giris: number; token_cikis: number };
  bugun: number;
  sinirlar: { aylik_uretim: number | null; gunluk_uretim: number | null; aylik_gonderi: number | null; marka_siniri: number | null; kredi_ile_asim: boolean };
  blok_uretim: number;
  blok_kredi: number;
  kredi_bakiyesi: number | null;
  ajans: boolean;
}

export interface Meta {
  yonetici: boolean;
  hesap: string | null;
  kisi: string;
  sahte_mod: boolean;
  ai_hazir: boolean;
  kanallar: string[];
  sinirlar: Record<string, Record<string, number>>;
  gorsel_onerileri: Record<string, { boyut: string; oran: string }[]>;
  baglanti_ayri: string[];
  ton_olcekleri: string[];
  politikalar: Politika[];
  ince_ayarlar: InceAyar[];
  diller: string[];
  en_cok_varyasyon: number;
  hazir_sablonlar: Sablon[];
  uyari_turleri: string[];
  durumlar: Durum[];
  gecisler: Record<string, Durum[]>;
  varsayilan_saat_dilimi: string;
  csv_sutunlari: string[];
  kullanim: Kullanim;
}

export interface Marka {
  id: number;
  hesap_email: string | null;
  ad: string;
  sektor: string;
  hedef_kitle: string;
  ton: Record<string, number>;
  yapilacaklar: string[];
  yapilmayacaklar: string[];
  yasakli_kelimeler: string[];
  ornek_metinler: string[];
  anahtar_mesajlar: string[];
  emoji_politikasi: Politika;
  hashtag_politikasi: Politika;
  hashtagler: string[];
  diller: string[];
}

export interface SesOnerisi {
  ozet: string;
  ton: Record<string, number>;
  yapilacaklar: string[];
  yapilmayacaklar: string[];
  anahtar_mesajlar: string[];
  emoji_politikasi: Politika;
  hashtag_politikasi: Politika;
}

export interface AlanOlcumu {
  alan: string;
  indeks?: number;
  uzunluk?: number;
  adet?: number;
  sinir?: number | null;
  en_az?: number;
  en_cok?: number;
  asim: boolean;
}

export interface Varyasyon {
  metin: string;
  alanlar: Record<string, unknown>;
  olcum: AlanOlcumu[];
  kanal_olcumu: Olcum | null;
  uyarilar: Uyari[];
}

export interface Uretim {
  id: number;
  sablon: string;
  kanal: string | null;
  islem: string;
  kaynak_id: number | null;
  dil: string;
  marka_id: number | null;
  girdi: Record<string, string>;
  varyasyonlar: Varyasyon[];
  model: string | null;
  sahte: boolean;
  kredi: number;
  created_at: string | null;
}

export interface OnayBilgisi {
  islem_id: number;
  durum: 'bekliyor' | 'kullanildi' | 'iptal' | 'suresi_doldu' | string;
  son_kullanma: string | null;
  alici: string;
}

export interface Gorsel {
  anahtar: string;
  url: string;
  ad: string;
  tur?: string;
  genislik?: number;
  yukseklik?: number;
}

/** Faz 7K — gönderiye bağlanabilecek proje (`acik`: kapanmamış; hesabın tek açık projesi öneriliyor). */
export interface GonderiProjesi {
  id: number;
  baslik: string;
  hesap: string | null;
  acik: boolean;
}

export interface Gonderi {
  id: number;
  hesap_email: string | null;
  yoneten: 'ajans' | 'musteri';
  baslik: string;
  metin: string;
  kanallar: string[];
  kanal_metinleri: Record<string, string>;
  hashtagler: string;
  ilk_yorum: string;
  gorseller: Gorsel[];
  video_url: string;
  baglanti: string;
  kisa_linkler: Record<string, { qr_id: number; kod: string; adres: string }>;
  kampanya: string;
  notlar: string;
  marka_id: number | null;
  marka_adi: string | null;
  /** Faz 7K — isteğe bağlı proje (otomasyon "İçerik onaylandı → Paylaş" görevi buraya açılır). */
  proje_id: number | null;
  sorumlu_eposta: string;
  olusturan_eposta: string;
  durum: Durum;
  durum_notu: string;
  durum_at: string | null;
  durum_degistiren: string;
  gecisler: Durum[];
  saat_dilimi: string;
  planlanan: string | null;
  planlanan_at: string | null;
  gun: string | null;
  onaylayan: string;
  onay_at: string | null;
  yayinlandi_at: string | null;
  hatirlatma_at: string | null;
  uretim_id: number | null;
  uyarilar: Uyari[];
  olcumler: Record<string, Olcum>;
  onay?: OnayBilgisi | null;
}

export interface GonderiListesi {
  items: Gonderi[];
  saat_dilimi: string;
  kampanyalar: string[];
  sinirda: boolean;
}

export interface Paket {
  gonderi_id: number;
  baslik: string;
  kanallar: KanalOzeti[];
  gorseller: Gorsel[];
  video_url: string;
  planlanan: string | null;
  planlanan_at: string | null;
  saat_dilimi: string;
  durum: Durum;
}

export interface GenelAyarlar {
  model: string;
  model_ayari: string;
  gunluk_butce: number;
  blok_uretim: number;
  blok_kredi: number;
  ajans_gunluk: number;
}

export interface HesapSecenegi {
  eposta: string;
  ad: string | null;
  modul_acik: boolean;
}

export class StudyoHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): StudyoHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new StudyoHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new StudyoHatasi(durum, 'cok_hizli');
  if (durum === 404) return new StudyoHatasi(durum, 'bulunamadi');
  if (durum === 403) return new StudyoHatasi(durum, 'yetki');
  return new StudyoHatasi(durum, durum === 0 ? 'ag' : 'genel');
}

function govdeyiAc<T>(yanit: unknown): T {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T;
}

async function istek<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    return govdeyiAc<T>(await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> | undefined }));
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

async function hamIstek(url: string, init: RequestInit = {}): Promise<Response> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, { ...init, headers: { ...oturumBasliklari(), ...(init.headers as Record<string, string> | undefined) } });
  } catch {
    throw new StudyoHatasi(0, 'ag');
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

export interface Suzgec {
  /** Yalnız yönetici: "*" = bütün hesaplar (seçili hesabı ezer). */
  hesap?: string;
  bas?: string;
  bit?: string;
  tz?: string;
  kanal?: string;
  kampanya?: string;
  durum?: string;
  marka_id?: number;
  tarihsiz?: boolean;
}

export function studyoApi(mod: StudyoMod, hesap: string | null = null) {
  const T = mod === 'yonetici' ? '/api/v1/icerik-studyosu/yonetim' : '/api/v1/icerik-studyom';
  const h = mod === 'yonetici' ? hesap : null;
  const q = (o: Record<string, string | number | boolean | undefined | null> = {}) => {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries({ ...o, hesap: o.hesap ?? h })) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
    const s = p.toString();
    return s ? `?${s}` : '';
  };
  const govde = <G extends Record<string, unknown>>(g: G) => (h ? { ...g, hesap: h } : g);
  return {
    mod,
    hesap: h,
    meta: () => istek<Meta>('GET', `${T}/meta${q()}`),
    kullanim: () => istek<Kullanim>('GET', `${T}/kullanim${q()}`),
    markalar: () => istek<{ items: Marka[]; sinir: number | null }>('GET', `${T}/markalar${q()}`),
    /** Gönderiye bağlanabilecek projeler; yönetici `hesap` verirse o hesabınki ("*" = ajansın kendi içeriği: hepsi). */
    projeler: (hesap?: string | null) =>
      istek<{ items: GonderiProjesi[]; hesap: string | null }>('GET', `${T}/projeler${q(mod === 'yonetici' && hesap !== undefined ? { hesap: hesap ?? '*' } : {})}`),
    markaEkle: (g: Partial<Marka>) => istek<Marka>('POST', `${T}/markalar`, govde(g as Record<string, unknown>)),
    markaGuncelle: (id: number, g: Partial<Marka>) => istek<Marka>('PUT', `${T}/markalar/${id}`, g),
    markaSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/markalar/${id}`),
    sesCikar: (id: number, dil: string) => istek<{ oneri: SesOnerisi; kullanim: Kullanim }>('POST', `${T}/markalar/${id}/ses-cikar`, { dil }),
    sablonlar: () => istek<{ hazir: Sablon[]; ozel: Sablon[] }>('GET', `${T}/sablonlar${q()}`),
    sablonEkle: (g: Record<string, unknown>) => istek<Sablon>('POST', `${T}/sablonlar`, govde(g)),
    sablonGuncelle: (id: number, g: Record<string, unknown>) => istek<Sablon>('PUT', `${T}/sablonlar/${id}`, g),
    sablonSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/sablonlar/${id}`),
    uret: (g: { sablon: string; girdi: Record<string, string>; marka_id?: number | null; kanal?: string | null; varyasyon: number; dil: string }) =>
      istek<{ uretim: Uretim; kullanim: Kullanim }>('POST', `${T}/uret`, govde(g)),
    inceAyar: (g: { islem: InceAyar; metin: string; kanal?: string | null; marka_id?: number | null; hedef_dil?: string; dil?: string; kaynak_id?: number | null }) =>
      istek<{ uretim: Uretim; kullanim: Kullanim }>('POST', `${T}/ince-ayar`, govde(g)),
    uretimler: (sinir = 30) => istek<{ items: Uretim[] }>('GET', `${T}/uretimler${q({ sinir })}`),
    gonderiler: (s: Suzgec = {}) => istek<GonderiListesi>('GET', `${T}/gonderiler${q({ ...s })}`),
    gonderi: (id: number) => istek<Gonderi>('GET', `${T}/gonderiler/${id}`),
    gonderiEkle: (g: Record<string, unknown>) => istek<Gonderi>('POST', `${T}/gonderiler`, govde(g)),
    gonderiGuncelle: (id: number, g: Record<string, unknown>) => istek<Gonderi>('PUT', `${T}/gonderiler/${id}`, g),
    gonderiSil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/gonderiler/${id}`),
    durum: (id: number, durum: Durum, not?: string) => istek<Gonderi>('POST', `${T}/gonderiler/${id}/durum`, { durum, not: not || null }),
    kisaLink: (id: number) => istek<{ kisa_linkler: Gonderi['kisa_linkler']; gonderi: Gonderi }>('POST', `${T}/gonderiler/${id}/kisa-link`),
    paket: (id: number) => istek<Paket>('GET', `${T}/gonderiler/${id}/paket`),
    onayaGonder: (id: number, g: { gun?: number; eposta_gonder?: boolean }) =>
      istek<{ baglanti: string; eposta_gonderildi: boolean; son_kullanma: string; gonderi: Gonderi }>('POST', `${T}/gonderiler/${id}/onaya-gonder`, g),
    gorseller: () => istek<{ items: Gorsel[] }>('GET', `${T}/gorseller${q()}`),
    async gorselYukle(dosya: File): Promise<Gorsel> {
      const f = new FormData();
      f.append('dosya', dosya);
      return (await hamIstek(`${T}/gorseller${q()}`, { method: 'POST', body: f })).json();
    },
    async zipIndir(id: number): Promise<void> {
      blobIndir(await (await hamIstek(`${T}/gonderiler/${id}/gorseller.zip`)).blob(), `icerik-${id}-gorseller.zip`);
    },
    async csvIndir(s: Suzgec): Promise<void> {
      blobIndir(await (await hamIstek(`${T}/disa-aktar.csv${q({ ...s })}`)).blob(), 'icerik-plani.csv');
    },
    ayarlar: () => istek<GenelAyarlar>('GET', `${T}/ayarlar`),
    ayarlarYaz: (g: Partial<GenelAyarlar>) => istek<GenelAyarlar>('PUT', `${T}/ayarlar`, g),
    hesaplar: () => istek<{ items: HesapSecenegi[] }>('GET', `${T}/hesaplar`),
  };
}
export type StudyoApi = ReturnType<typeof studyoApi>;

/** 5M kampanya düzenleyicisine "aktar": bülten şablonu çıktısından taslak kampanya. */
export async function kampanyayaAktar(mod: StudyoMod, alanlar: Record<string, unknown>, ad: string): Promise<{ id: number }> {
  const T = mod === 'yonetici' ? '/api/v1/eposta-pazarlama/yonetim' : '/api/v1/eposta-pazarlamam';
  const s = (x: unknown) => (typeof x === 'string' ? x : '');
  const bloklar: Record<string, unknown>[] = [];
  if (s(alanlar.baslik)) bloklar.push({ tur: 'baslik', metin: s(alanlar.baslik).slice(0, 200), seviye: 1 });
  if (s(alanlar.govde)) bloklar.push({ tur: 'metin', metin: s(alanlar.govde) });
  return istek<{ id: number }>('POST', `${T}/kampanyalar`, {
    ad: ad.slice(0, 160) || 'İçerik stüdyosu',
    konu: s(alanlar.konu).slice(0, 200),
    onizleme_metni: s(alanlar.onizleme).slice(0, 200),
    bloklar,
  });
}

/**
 * Zamanı geçmiş ama paylaşılmamış gönderileri yöneticilere e-postayla bildirir (eski içerik
 * takviminin "Hatırlat" düğmesi; uç `/api/v1/content-reminder`, yalnız yönetici). Uç e-posta
 * gitmese de 200 döner — `eposta_durumu` "sent" değilse panel bunu açıkça söylüyor.
 */
export interface HatirlatmaSonucu {
  geciken: number;
  eposta_durumu: string;
  eposta_ayrinti: string;
  alici_sayisi: number;
  metin: string;
}
export function gecikenleriHatirlat(): Promise<HatirlatmaSonucu> {
  return istek<HatirlatmaSonucu>('POST', '/api/v1/content-reminder', {});
}

export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof StudyoHatasi) {
    return t(`icerikStudyosu.hata.${e.kod}`, { ...e.ek, defaultValue: t('icerikStudyosu.hata.genel') }) as string;
  }
  return t('icerikStudyosu.hata.genel');
}

export async function panoyaKopyala(metin: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(metin);
      return true;
    }
  } catch {
    /* yedeğe düş */
  }
  try {
    const alan = document.createElement('textarea');
    alan.value = metin;
    alan.setAttribute('readonly', '');
    alan.style.position = 'fixed';
    alan.style.opacity = '0';
    document.body.appendChild(alan);
    alan.select();
    const tamam = document.execCommand('copy');
    alan.remove();
    return tamam;
  } catch {
    return false;
  }
}

/** Karakter sayımı ön yüzde (canlı gösterge): sunucuyla aynı kural (X: bağlantı 23, CJK 2). */
export function uzunluk(s: string, platform?: string | null): number {
  if (platform !== 'x') return Array.from(s || '').length;
  const genis = (c: string) => /[ᄀ-ᅟ⺀-꓏가-힣豈-﫿︰-﹏＀-｠￠-￦]/.test(c);
  let toplam = 0;
  const parcalar = (s || '').split(/(https?:\/\/\S+)/i);
  for (const p of parcalar) {
    if (/^https?:\/\//i.test(p)) toplam += 23;
    else for (const c of Array.from(p)) toplam += genis(c) ? 2 : 1;
  }
  return toplam;
}

// ---------------------------------------------------------------------------
// Tarih yardımcıları (takvim)
// ---------------------------------------------------------------------------
export const gunAnahtari = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function gunEkle(d: Date, n: number): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() + n);
  return x;
}

/** Haftanın ilk günü (Pazartesi). */
export function haftaBasi(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const g = (x.getDay() + 6) % 7;
  return gunEkle(x, -g);
}

export function tarihSaatYaz(iso: string | null | undefined, dil: string, tz?: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short', timeZone: tz }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function saatYaz(iso: string | null | undefined, dil: string, tz?: string): string {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(dil, { hour: '2-digit', minute: '2-digit', timeZone: tz }).format(new Date(iso));
  } catch {
    return '';
  }
}

/** Tarayıcının saat dilimi (yoksa sunucu varsayılanı). */
export function tarayiciSaatDilimi(varsayilan: string): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || varsayilan;
  } catch {
    return varsayilan;
  }
}
