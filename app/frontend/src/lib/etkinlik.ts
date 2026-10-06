import type { TFunction } from 'i18next';

import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';
import type { Bicim, EtkinlikDili, EtkinlikDurumu, OkutmaYaniti, Oturum, Sayac, Soru, TelefonKurali } from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — Etkinlik ve bilet: panel uçları.
 *
 * Yönetici `/api/v1/etkinlik/yonetim/...`, müşteri `/api/v1/etkinliklerim/...` (etkin hesap
 * `X-MK-Hesap` başlığıyla). İki panel aynı bileşeni kullanıyor; yalnız taban yol değişiyor.
 * Bu dosya yalnız sekme açıldığında (lazy) iniyor.
 */

export type EtkinlikMod = 'yonetici' | 'musteri';

export interface Etkinlik {
  id: number;
  hesap_email: string | null;
  ajans: boolean;
  slug: string;
  adres_url: string;
  baslik: string;
  ozet: string;
  aciklama: string;
  kapak: string | null;
  renk: string;
  bicim: Bicim;
  mekan_adi: string;
  adres: string;
  harita_url: string;
  online_baglanti: string;
  saat_dilimi: string;
  baslangic: string;
  bitis: string;
  oturumlar: Oturum[];
  kapasite: number | null;
  kayit_acilis: string | null;
  kayit_kapanis: string | null;
  durum: EtkinlikDurumu;
  dil: EtkinlikDili;
  organizator_ad: string;
  organizator_eposta: string;
  organizator_url: string;
  iade_politikasi: string;
  kvkk_metni: string;
  odeme_notu: string;
  arama_motoru: boolean;
  listede_goster: boolean;
  katilimci_adlari: boolean;
  telefon: TelefonKurali;
  sorular: Soru[];
  bekleme_listesi: boolean;
  iptal_sinir_saat: number;
  saklama_gun: number;
  tesekkur_aktif: boolean;
  tesekkur_metni: string;
  anket_url: string;
  tesekkur_at: string | null;
  bilet_sayisi?: number;
  giren?: number;
  satilan?: number;
  kalan?: number | null;
  kapasite_siniri?: number | null;
}

export interface Meta {
  yonetici: boolean;
  ucretli_bilet: boolean;
  /** Ödeme sağlayıcısı anahtarları tanımlı mı (değilse fiyat alanı kapalı + açıklama). */
  odeme_hazir: boolean;
  aylik_etkinlik_siniri: number | null;
  bu_ay: number | null;
  kapasite_siniri: number | null;
  bicimler: Bicim[];
  durumlar: EtkinlikDurumu[];
  para_birimleri: string[];
  telefon_secenekleri: TelefonKurali[];
  soru_turleri: Soru['tur'][];
  en_cok_soru: number;
  en_cok_adet: number;
  diller: EtkinlikDili[];
  adres_tabani: string;
  widget_adresi: string;
  varsayilan_saat_dilimi: string;
  odeme_suresi_dk: number;
}

export interface BiletTuru {
  id: number;
  etkinlik_id: number;
  ad: string;
  aciklama: string;
  fiyat: number;
  para_birimi: string;
  kontenjan: number | null;
  satis_bas: string | null;
  satis_bit: string | null;
  kisi_basi_en_cok: number;
  gizli: boolean;
  gizli_kod: string;
  aktif: boolean;
  sira: number;
  satilan: number | null;
  kalan: number | null;
}

export interface IndirimKodu {
  id: number;
  kod: string;
  tur: 'yuzde' | 'tutar';
  deger: number;
  kullanim_siniri: number | null;
  kullanilan: number;
  bilet_turleri: number[];
  son_tarih: string | null;
  aktif: boolean;
}

export interface Katilimci {
  id: number;
  kod: string;
  tur_id: number;
  tur_adi: string;
  katilimci_ad: string | null;
  durum: 'gecerli' | 'odeme_bekliyor' | 'iptal';
  giris_at: string | null;
  iade: 'yok' | 'bekliyor' | 'yapildi';
  fiyat: number;
  iptal_at: string | null;
  iptal_eden: string | null;
  siparis: {
    id: number;
    kod: string;
    ad: string | null;
    eposta: string | null;
    telefon: string | null;
    durum: string;
    kaynak: string;
    toplam: number;
    indirim: number;
    para_birimi: string;
    odeme_son: string | null;
    odendi_at: string | null;
    pazarlama_izni: boolean;
    anonim: boolean;
    created_at: string | null;
    crm_aday_id: number | null;
    yanitlar: { id: string; soru: string; yanit: string | boolean }[];
  };
}

export interface BeklemeKaydi {
  id: number;
  ad: string | null;
  eposta: string | null;
  telefon: string | null;
  adet: number;
  tur_id: number | null;
  durum: 'bekliyor' | 'davet' | 'kullanildi' | 'suresi_doldu' | 'iptal';
  davet_at: string | null;
  davet_son: string | null;
  siparis_id: number | null;
  created_at: string | null;
}

export interface Istatistik extends Sayac {
  bekleyen_odeme: number;
  bekleme: Record<string, number>;
  son_okutmalar: { zaman: string; sonuc: string; kaynak: string; kod: string | null; tur: string | null; cevrimdisi: boolean }[];
}

export interface Satis {
  para_birimi: string;
  gelir: number;
  indirim: number;
  bekleyen_odeme: { sayi?: number; toplam?: number };
  siparisler: Record<string, { sayi: number; toplam: number; indirim: number }>;
  iade: Record<string, number>;
  turler: { id: number; ad: string; fiyat: number; para_birimi: string; gecerli: number; brut: number; bekleyen: number; iptal: number }[];
  indirim_kodlari: { kod: string; kullanilan: number; kullanim_siniri: number | null }[];
}

export interface ListeAyari {
  kapsam: string;
  slug: string;
  baslik: string;
  aciklama: string;
  acik: boolean;
  adres_url: string | null;
}

export class EtkinlikUcHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public alan: string | null = null,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): EtkinlikUcHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, alan, ...ek } = detay as { kod: string; alan?: string } & Record<string, unknown>;
    return new EtkinlikUcHatasi(durum, kod, alan ?? null, ek);
  }
  if (durum === 429) return new EtkinlikUcHatasi(durum, 'cok_hizli');
  if (durum === 404) return new EtkinlikUcHatasi(durum, 'bulunamadi');
  return new EtkinlikUcHatasi(durum, durum === 0 ? 'ag' : 'genel');
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
    throw new EtkinlikUcHatasi(0, 'ag');
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

export function etkinlikApi(mod: EtkinlikMod) {
  const T = mod === 'yonetici' ? '/api/v1/etkinlik/yonetim' : '/api/v1/etkinliklerim';
  const E = (id: number) => `${T}/${id}`;
  return {
    taban: T,
    meta: () => istek<Meta>('GET', `${T}/meta`),
    liste: (hesap?: string) => istek<{ items: Etkinlik[]; toplam: number }>('GET', `${T}${hesap ? `?hesap=${encodeURIComponent(hesap)}` : ''}`),
    girisListesi: () =>
      istek<{ items: { id: number; baslik: string; baslangic: string; bitis: string; saat_dilimi: string; durum: string; hesap_email: string | null }[] }>(
        'GET',
        `${T}/giris-listesi`
      ),
    olustur: (g: Record<string, unknown>) => istek<Etkinlik>('POST', T, g),
    getir: (id: number) => istek<Etkinlik>('GET', E(id)),
    guncelle: (id: number, g: Record<string, unknown>) => istek<Etkinlik>('PUT', E(id), g),
    sil: (id: number) => istek<{ ok: boolean }>('DELETE', E(id)),
    async kapakYukle(id: number, dosya: File): Promise<Etkinlik> {
      const form = new FormData();
      form.append('dosya', dosya);
      const y = await hamIstek(`${E(id)}/kapak`, { method: 'POST', body: form });
      return (await y.json()) as Etkinlik;
    },
    kapakSil: (id: number) => istek<Etkinlik>('DELETE', `${E(id)}/kapak`),
    async qrBlob(id: number, bicim: 'png' | 'svg'): Promise<Blob> {
      return (await hamIstek(`${E(id)}/qr?bicim=${bicim}`, { method: 'GET' })).blob();
    },
    turler: (id: number) => istek<{ items: BiletTuru[] }>('GET', `${E(id)}/bilet-turleri`),
    turOlustur: (id: number, g: Partial<BiletTuru>) => istek<BiletTuru>('POST', `${E(id)}/bilet-turleri`, g),
    turGuncelle: (id: number, tid: number, g: Partial<BiletTuru>) => istek<BiletTuru>('PUT', `${E(id)}/bilet-turleri/${tid}`, g),
    turSil: (id: number, tid: number) => istek<{ ok: boolean }>('DELETE', `${E(id)}/bilet-turleri/${tid}`),
    indirimler: (id: number) => istek<{ items: IndirimKodu[] }>('GET', `${E(id)}/indirimler`),
    indirimOlustur: (id: number, g: Partial<IndirimKodu>) => istek<IndirimKodu>('POST', `${E(id)}/indirimler`, g),
    indirimGuncelle: (id: number, iid: number, g: Partial<IndirimKodu>) => istek<IndirimKodu>('PUT', `${E(id)}/indirimler/${iid}`, g),
    indirimSil: (id: number, iid: number) => istek<{ ok: boolean }>('DELETE', `${E(id)}/indirimler/${iid}`),
    katilimcilar: (id: number, q: Record<string, string> = {}) => {
      const p = new URLSearchParams();
      for (const [k, v] of Object.entries(q)) if (v) p.set(k, v);
      return istek<{ items: Katilimci[]; toplam: number }>('GET', `${E(id)}/katilimcilar?${p.toString()}`);
    },
    async csvBlob(id: number): Promise<Blob> {
      return (await hamIstek(`${E(id)}/katilimcilar.csv`, { method: 'GET' })).blob();
    },
    katilimciEkle: (id: number, g: Record<string, unknown>) => istek<{ ok: boolean; kod: string }>('POST', `${E(id)}/katilimcilar`, g),
    siparisIptal: (id: number, sid: number, g: { iade?: boolean; bildir?: boolean; neden?: string }) =>
      istek<{ ok: boolean }>('POST', `${E(id)}/siparisler/${sid}/iptal`, g),
    siparisOdendi: (id: number, sid: number) => istek<{ ok: boolean }>('POST', `${E(id)}/siparisler/${sid}/odendi`),
    biletIptal: (id: number, bid: number, g: { iade?: boolean; bildir?: boolean }) => istek<{ ok: boolean }>('POST', `${E(id)}/biletler/${bid}/iptal`, g),
    biletIade: (id: number, bid: number, durum: Katilimci['iade']) => istek<{ ok: boolean }>('POST', `${E(id)}/biletler/${bid}/iade`, { durum }),
    biletGiris: (id: number, bid: number) => istek<OkutmaYaniti>('POST', `${E(id)}/biletler/${bid}/giris`),
    biletGirisGeri: (id: number, bid: number) => istek<{ ok: boolean }>('DELETE', `${E(id)}/biletler/${bid}/giris`),
    bekleme: (id: number) => istek<{ items: BeklemeKaydi[] }>('GET', `${E(id)}/bekleme`),
    beklemeDavet: (id: number, wid: number) => istek<{ ok: boolean }>('POST', `${E(id)}/bekleme/${wid}/davet`),
    beklemeSil: (id: number, wid: number) => istek<{ ok: boolean }>('DELETE', `${E(id)}/bekleme/${wid}`),
    istatistik: (id: number) => istek<Istatistik>('GET', `${E(id)}/istatistik`),
    satis: (id: number) => istek<Satis>('GET', `${E(id)}/satis`),
    duyuru: (id: number, g: { konu: string; metin: string }) => istek<{ ok: boolean; alici: number }>('POST', `${E(id)}/duyuru`, g),
    tesekkur: (id: number) => istek<{ ok: boolean }>('POST', `${E(id)}/tesekkur`),
    gorevli: (id: number) => istek<{ adres: string; son: string; surum: number }>('GET', `${E(id)}/gorevli`),
    gorevliYeni: (id: number, g: { saat?: number | null; yenile?: boolean }) => istek<{ adres: string; son: string; surum: number }>('POST', `${E(id)}/gorevli`, g),
    pazarlama: (id: number) => istek<{ acik: boolean; izinli: number; listeler: { id: number; ad: string }[] }>('GET', `${E(id)}/pazarlama`),
    pazarlamaAktar: (id: number, liste_id: number) =>
      istek<{ sayilar: { aktarilan: number; yeni: number; listeye: number; reddetmis: number } }>('POST', `${E(id)}/pazarlama`, { liste_id }),
    listeAyari: (hesap?: string | null) => istek<ListeAyari>('GET', `${T}/liste-ayari${hesap ? `?hesap=${encodeURIComponent(hesap)}` : ''}`),
    listeAyariYaz: (g: Partial<ListeAyari>, hesap?: string | null) =>
      istek<ListeAyari>('PUT', `${T}/liste-ayari${hesap ? `?hesap=${encodeURIComponent(hesap)}` : ''}`, g),
  };
}

export type EtkinlikApi = ReturnType<typeof etkinlikApi>;

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof EtkinlikUcHatasi) {
    return t(`etkinlik.hata.${e.kod}`, { ...e.ek, defaultValue: t('etkinlik.hata.genel') }) as string;
  }
  return t('etkinlik.hata.genel');
}

/** `datetime-local` değeri ↔ ISO (etkinliğin saat diliminde). */
export function yerelGirdi(iso: string | null | undefined, tz: string): string {
  if (!iso) return '';
  try {
    const p = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(iso));
    const v = (t: string) => p.find((x) => x.type === t)?.value || '00';
    return `${v('year')}-${v('month')}-${v('day')}T${v('hour')}:${v('minute')}`;
  } catch {
    return iso.slice(0, 16);
  }
}

/** "2026-11-05T10:00" (saat dilimindeki yerel) → UTC ISO. Yaz saatli bölgelerde de doğru (iki geçişli düzeltme). */
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
