import { client } from '@/lib/sdkClient';

/**
 * Faz 6R — sektör paketini tek tıkla açma + hazır sektör ayarları (yalnız yönetici).
 *
 * Uçlar `app/backend/routers/sektor_paketi.py`; paket/set tanımları sunucuda
 * (`core/sektor_paketleri.py`, `core/sektor_ayarlari.py`). Paket ve set adları vitrin
 * ek paketinden (`modulVitrini.p.<paket>.ad`, `modulVitrini.s.<set>.ad`).
 */

export type ModulEtkisi = 'plana_dahil' | 'ayri_satilan' | 'ust_pakette';

export interface KatalogPaketi {
  anahtar: string;
  slug: string;
  ikon: string;
  moduller: string[];
  setler: string[];
  acilacak: string[];
}

export interface KatalogSeti {
  anahtar: string;
  paket: string;
  ikon: string;
  kvkk_ozel: boolean;
  moduller: string[];
  otomasyon: string[];
}

export interface Katalog {
  paketler: KatalogPaketi[];
  setler: KatalogSeti[];
  diller: string[];
  icerik_dilleri: string[];
}

export interface OnizlemeModulu {
  anahtar: string;
  ad_anahtari: string;
  ikon: string;
  durum: 'acilacak' | 'acik';
  kaynak: string;
  paketten: boolean;
  bagimliliklar: string[];
  etki: ModulEtkisi;
  paketler: string[];
  en_dusuk_paket: string | null;
  kredi: boolean;
}

export interface HazirOge {
  tur: string;
  ad: string;
  sure_dk?: number;
  tampon_dk?: number;
  kapasite?: number;
  aktif?: boolean;
  soru_sayisi?: number;
  sayi?: number;
  madde_sayisi?: number;
  adim_sayisi?: number;
  hizmet_sayisi?: number;
  bekle_gun?: number;
  taslak?: boolean;
}

export interface Atlanan {
  neden: string;
  sayi?: number;
  sinir?: number;
  ad?: string;
  oneri?: string;
  modul?: string;
}

export interface HazirBolum {
  modul: string;
  ogeler: HazirOge[];
  atlanan: Atlanan[];
}

export interface Onizleme {
  eposta: string;
  paket: string | null;
  set: string;
  dil: string;
  icerik_dili: string;
  musteri_paketi: string | null;
  moduller: OnizlemeModulu[];
  ozet: { acilacak: number; zaten_acik: number; ayri_satilan: number; kredi: string[]; olusturulacak: number };
  hazir: HazirBolum[];
  uyarilar: string[];
  oneriler: string[];
}

export interface Uygulama {
  id: number;
  eposta: string;
  tur: 'paket' | 'hazir';
  paket: string | null;
  set: string | null;
  dil: string;
  icerik_dili: string;
  durum: 'uygulandi' | 'kaldirildi';
  hazir_durum: 'yok' | 'uygulandi' | 'geri_alindi';
  acilan_moduller: { anahtar: string; onceki_elle: boolean | null; acilis_at?: string }[];
  zaten_acik: string[];
  hazir_kayitlar: { modul: string; tablo: string; id: number; etiket: string; tur?: string }[];
  atlananlar: Atlanan[];
  oneriler: string[];
  geri_alma: {
    kapatilan?: string[];
    korunan?: { anahtar: string; neden: string; moduller?: string[] }[];
    hazir?: GeriAlmaSonucu | null;
  } | null;
  bildirim: boolean;
  uygulayan: string | null;
  geri_alan: string | null;
  olusturma: string | null;
  kaldirma: string | null;
  hazir_geri_alma: string | null;
}

export interface GeriAlmaSonucu {
  silinen: { modul: string; etiket: string; tablo: string; zaten_yok?: boolean }[];
  korunan: { modul: string; etiket: string; tablo: string; neden: string }[];
}

export interface MusteriBilgisi {
  eposta: string;
  varsayilan: { dil: string; isletme_adi: string; adres: string };
  gecmis: Uygulama[];
}

export interface UygulamaSonucu {
  uygulama: Uygulama | null;
  plan: HazirBolum[];
  uyarilar: string[];
}

export interface KaldirmaSonucu {
  uygulama: Uygulama;
  kapatilan: string[];
  korunan: { anahtar: string; neden: string; moduller?: string[] }[];
  hazir: GeriAlmaSonucu | null;
}

export interface PaketGirdisi {
  paket?: string | null;
  set?: string | null;
  dil?: string;
  isletme_adi?: string;
  adres?: string;
  hazir_ayarlar?: boolean;
  bildirim?: boolean;
}

/** Uçtan dönen hata; `kod` sunucunun `detail.kod` değeri (`hazir_ayar_hatasi` → `modul` de gelir). */
export class PaketHatasi extends Error {
  durum: number;
  kod: string;
  modul?: string;

  constructor(durum: number, kod: string, modul?: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
    this.modul = modul;
  }
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    const durum = h?.response?.status ?? h?.status ?? 0;
    const detay = h?.response?.data?.detail;
    if (detay && typeof detay === 'object') {
      const d = detay as { kod?: unknown; modul?: unknown };
      throw new PaketHatasi(durum, typeof d.kod === 'string' ? d.kod : 'genel', typeof d.modul === 'string' ? d.modul : undefined);
    }
    throw new PaketHatasi(durum, 'genel');
  }
}

const U = '/api/v1/sektor-paketleri';
const m = (eposta: string) => `${U}/musteri/${encodeURIComponent(eposta)}`;

export function katalogGetir(): Promise<Katalog> {
  return istek<Katalog>('GET', U);
}

export function musteriBilgisiGetir(eposta: string): Promise<MusteriBilgisi> {
  return istek<MusteriBilgisi>('GET', m(eposta));
}

export function onizle(eposta: string, girdi: PaketGirdisi): Promise<Onizleme> {
  return istek<Onizleme>('POST', `${m(eposta)}/onizleme`, { ...girdi });
}

export function paketiUygula(eposta: string, girdi: PaketGirdisi): Promise<UygulamaSonucu> {
  return istek<UygulamaSonucu>('POST', `${m(eposta)}/uygula`, { ...girdi });
}

export function hazirAyarlariUygula(eposta: string, girdi: PaketGirdisi): Promise<UygulamaSonucu> {
  return istek<UygulamaSonucu>('POST', `${m(eposta)}/hazir`, { ...girdi });
}

export function paketiKaldir(uid: number, girdi: { hazir_ayarlar: boolean; bildirim: boolean }): Promise<KaldirmaSonucu> {
  return istek<KaldirmaSonucu>('POST', `${U}/uygulamalar/${uid}/kaldir`, { ...girdi });
}

export function hazirAyarlariGeriAl(uid: number): Promise<{ uygulama: Uygulama; hazir: GeriAlmaSonucu }> {
  return istek<{ uygulama: Uygulama; hazir: GeriAlmaSonucu }>('POST', `${U}/uygulamalar/${uid}/hazir-geri-al`);
}
