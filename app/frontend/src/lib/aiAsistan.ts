import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 5A — AI asistan + bilgi bankası: panel uçları.
 *
 * Yönetici `/api/v1/ai-asistan/yonetim/...`, müşteri `/api/v1/ai-asistanim/...`
 * (etkin hesap `X-MK-Hesap` başlığıyla). İki panel aynı bileşeni kullanıyor;
 * yalnız taban yol değişiyor. Bu dosya yalnız sekme açıldığında (lazy) iniyor.
 */

export type AsistanMod = 'yonetici' | 'musteri';
export type Dil = 'tr' | 'en' | 'de' | 'ru' | 'zh' | 'hi' | 'ar';
export type KaynakTuru = 'metin' | 'sss' | 'belge' | 'url' | 'modul';

export interface Mesai {
  aktif: boolean;
  saat_dilimi: string;
  gunler: Record<string, [string, string][]>;
}

export interface Sinirlar {
  kaynak_siniri: number;
  sayfa_siniri: number;
  aylik_mesaj: number;
  gunluk_mesaj: number;
  kredi_ile_asim: boolean;
}

export interface Asistan {
  id: number;
  hesap_email: string | null;
  anahtar: string;
  adres: string;
  ad: string;
  karsilama: string;
  ton: 'resmi' | 'samimi';
  dil: 'otomatik' | Dil;
  renk: string;
  avatar: string | null;
  onerilen_sorular: string[];
  yanit_uzunlugu: 'kisa' | 'orta' | 'uzun';
  devir_esigi: number;
  yasakli_konular: string[];
  mesai: Mesai;
  izinli_kokenler: string[];
  tam_sayfa: boolean;
  aktif: boolean;
  saklama_gun: number;
  hibrit: boolean;
  aydinlatma_metni: string;
  aydinlatma_baglantisi: string;
  created_at: string | null;
  updated_at: string | null;
  kaynak_sayisi?: number;
  parca_sayisi?: number;
  sohbet_sayisi?: number;
  sinirlar?: Sinirlar;
  kaynak_kullanilan?: number;
  sayfa_kullanilan?: number;
}

export interface Meta {
  yonetici: boolean;
  diller: Dil[];
  dil_secenekleri: ('otomatik' | Dil)[];
  tonlar: Asistan['ton'][];
  uzunluklar: Asistan['yanit_uzunlugu'][];
  saklama_secenekleri: number[];
  kaynak_turleri: KaynakTuru[];
  url_kapsamlari: ('tek' | 'site_haritasi')[];
  belge_turleri: string[];
  belge_en_cok_mb: number;
  mesaj_siniri: number;
  sinir: Record<string, number>;
  metin_en_cok: number;
  widget_adresi: string;
  adres_tabani: string;
  gomme_hazir: boolean;
  sinirlar?: Sinirlar;
  kaynak_kullanilan?: number;
  sayfa_kullanilan?: number;
}

export interface Kaynak {
  id: number;
  asistan_id: number;
  tur: KaynakTuru;
  baslik: string;
  ayar: { url?: string; kapsam?: 'tek' | 'site_haritasi'; en_cok?: number; modul?: string; id?: number };
  dosya_adi: string | null;
  boyut: number | null;
  durum: 'isleniyor' | 'hazir' | 'hata';
  hata: string | null;
  parca_sayisi: number;
  karakter: number;
  sayfa_sayisi: number;
  haftalik_yenile: boolean;
  son_isleme_at: string | null;
  sonraki_yenileme_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  sss?: { soru: string; cevap: string }[];
  metin?: string;
  parcalar?: { baslik: string | null; metin: string; adres: string | null }[];
}

export interface SohbetOzeti {
  id: number;
  asistan_id: number;
  kaynak: 'gomulu' | 'sayfa' | 'onizleme';
  koken: string | null;
  dil: string | null;
  mesaj_sayisi: number;
  bilinmeyen_sayisi: number;
  durum: 'acik' | 'devredildi';
  devir: {
    ad: string | null;
    eposta: string | null;
    telefon: string | null;
    not: string | null;
    zaman: string | null;
    talep_id: number | null;
    aday_id: number | null;
  } | null;
  anonim: boolean;
  ilk_mesaj: string | null;
  created_at: string | null;
  son_mesaj_at: string | null;
}

export interface SohbetMesaji {
  id: number;
  rol: 'kullanici' | 'asistan' | 'sistem';
  metin: string;
  kaynaklar: { no: number; kaynak_id: number; baslik: string | null; adres: string | null }[];
  bilinmiyor: boolean;
  kapsama: number | null;
  zaman: string | null;
}

export interface Kullanim {
  gunluk: { gun: string; mesaj: number; ai_mesaj: number; token_giris: number; token_cikis: number; kredi: number; devir: number }[];
  ay: { mesaj: number; ai_mesaj: number; kredi: number; devir: number; token_giris: number; token_cikis: number };
  bugun: { mesaj: number };
  sinirlar: Sinirlar;
  blok_mesaj: number;
  blok_kredi: number;
  kredi_bakiyesi: number | null;
  ajans: boolean;
}

export interface GenelAyarlar {
  model: string;
  model_ayari: string;
  gunluk_butce: number;
  blok_mesaj: number;
  blok_kredi: number;
  ajans_gunluk: number;
  gomme_modeli: string;
  gomme_hazir: boolean;
}

export class AsistanUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): AsistanUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new AsistanUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new AsistanUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new AsistanUcHatasi(durum, 'bulunamadi');
  return new AsistanUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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

/** Oturum + etkin hesap başlıkları (dosya yükleme ve önizleme isteği düz fetch ile). */
export function oturumBasliklari(): Record<string, string> {
  const b: Record<string, string> = { ...hesapBasliklari() };
  try {
    const j = localStorage.getItem('token');
    if (j) b.Authorization = `Bearer ${j}`;
  } catch {
    /* depolama yok */
  }
  return b;
}

async function formGonder<T>(url: string, form: FormData): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, { method: 'POST', body: form, headers: oturumBasliklari() });
  } catch {
    throw new AsistanUcHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = (await yanit.json().catch(() => null)) as { detail?: unknown } | null;
    throw hataCoz(yanit.status, govde?.detail);
  }
  return (await yanit.json()) as T;
}

export function asistanApi(mod: AsistanMod) {
  const T = mod === 'yonetici' ? '/api/v1/ai-asistan/yonetim' : '/api/v1/ai-asistanim';
  return {
    taban: T,
    meta: () => istek<Meta>('GET', `${T}/meta`),
    liste: (hesap?: string) => istek<{ items: Asistan[]; toplam: number }>('GET', `${T}${hesap ? `?hesap=${encodeURIComponent(hesap)}` : ''}`),
    olustur: (g: { ad: string; hesap_email?: string }) => istek<Asistan>('POST', T, g),
    getir: (id: number) => istek<Asistan>('GET', `${T}/${id}`),
    guncelle: (id: number, g: Partial<Asistan>) => istek<Asistan>('PUT', `${T}/${id}`, g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}`),
    anahtarYenile: (id: number) => istek<Asistan>('POST', `${T}/${id}/anahtar`),
    avatarYukle: (id: number, dosya: File) => {
      const f = new FormData();
      f.append('dosya', dosya);
      return formGonder<Asistan>(`${T}/${id}/avatar`, f);
    },
    avatarSil: (id: number) => istek<Asistan>('DELETE', `${T}/${id}/avatar`),
    iceAktarim: (id: number) => istek<{ items: { modul: string; id: number; ad: string }[] }>('GET', `${T}/${id}/ice-aktarim`),
    kaynaklar: (id: number) =>
      istek<{ items: Kaynak[]; sinirlar: Sinirlar; kaynak_kullanilan: number; sayfa_kullanilan: number }>('GET', `${T}/${id}/kaynaklar`),
    kaynakEkle: (id: number, g: Record<string, unknown>) => istek<Kaynak>('POST', `${T}/${id}/kaynaklar`, g),
    belgeYukle: (id: number, dosya: File, baslik?: string) => {
      const f = new FormData();
      f.append('dosya', dosya);
      if (baslik) f.append('baslik', baslik);
      return formGonder<Kaynak>(`${T}/${id}/kaynaklar/belge`, f);
    },
    kaynak: (id: number, kid: number) => istek<Kaynak>('GET', `${T}/${id}/kaynaklar/${kid}`),
    kaynakGuncelle: (id: number, kid: number, g: Record<string, unknown>) => istek<Kaynak>('PUT', `${T}/${id}/kaynaklar/${kid}`, g),
    kaynakIsle: (id: number, kid: number) => istek<Kaynak>('POST', `${T}/${id}/kaynaklar/${kid}/isle`),
    kaynakSil: (id: number, kid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/kaynaklar/${kid}`),
    sohbetler: (id: number, durum = 'hepsi', sayfa = 1) =>
      istek<{ items: SohbetOzeti[]; toplam: number; sayfa_boyu: number; saklama_gun: number }>(
        'GET',
        `${T}/${id}/sohbetler?durum=${encodeURIComponent(durum)}&sayfa=${sayfa}`
      ),
    sohbet: (id: number, sid: number) => istek<SohbetOzeti & { mesajlar: SohbetMesaji[] }>('GET', `${T}/${id}/sohbetler/${sid}`),
    anonimlestir: (id: number, sid: number) => istek<SohbetOzeti>('POST', `${T}/${id}/sohbetler/${sid}/anonimlestir`),
    sohbetSil: (id: number, sid: number) => istek<{ ok: boolean }>('DELETE', `${T}/${id}/sohbetler/${sid}`),
    kullanim: (id: number, gun = 30) => istek<Kullanim>('GET', `${T}/${id}/kullanim?gun=${gun}`),
    genelAyarlar: () => istek<GenelAyarlar>('GET', '/api/v1/ai-asistan/yonetim/ayarlar'),
    genelAyarlariYaz: (g: Partial<GenelAyarlar>) => istek<GenelAyarlar>('PUT', '/api/v1/ai-asistan/yonetim/ayarlar', g),
  };
}

export type AsistanApi = ReturnType<typeof asistanApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof AsistanUcHatasi) {
    const alan = e.alan ? t(`aiAsistan.alan.${e.alan.split('.')[0]}`, { defaultValue: '' }) : '';
    const metin = t(`aiAsistan.hata.${e.kod}`, { ...e.ek, defaultValue: t('aiAsistan.hata.genel') }) as string;
    return alan ? `${alan}: ${metin}` : metin;
  }
  return t('aiAsistan.hata.genel');
}

/**
 * Gömme kodu: tek satır betik (anahtar + isteğe bağlı dil + balon rengi). Balon rengi koda
 * yazılır ki betik, ziyaretçi balona tıklamadan hiçbir ağ isteği yapmasın.
 */
export function gommeKodu(widget: string, anahtar: string, dil?: string, renk?: string): string {
  const r = renk && /^#[0-9a-f]{6}$/i.test(renk) ? ` data-renk="${renk.toLowerCase()}"` : '';
  return `<script src="${widget}" data-asistan="${anahtar}"${dil ? ` data-dil="${dil}"` : ''}${r} async></script>`;
}
