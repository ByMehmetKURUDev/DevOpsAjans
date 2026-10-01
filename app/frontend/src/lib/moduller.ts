import { client } from '@/lib/sdkClient';

/**
 * Modül kaydı (Faz 1F).
 *
 * Manifest sunucuda (`app/backend/core/moduller.py`); ön yüz yalnız sekme
 * anahtarı → bileşen eşlemesini ve ikon adı → lucide bileşeni eşlemesini
 * tutuyor. Müşteri paneli sekme çubuğunu `GET /api/v1/modullerim` yanıtından
 * çiziyor; yanıt gelmezse bugünkü bütün sekmeler gösteriliyor.
 */

export type ModulKategorisi = 'cekirdek' | 'hizmet' | 'icerik' | 'finans' | 'analiz' | 'dijital_kimlik' | 'is_araclari';
export type ModulDurumu = 'yayinda' | 'beta' | 'yakinda';
export type ModulKaynagi = 'varsayilan' | 'paket' | 'elle';
export type ModulGorunumu = 'acik' | 'yakinda' | 'eklenebilir';

export const KATEGORILER: ModulKategorisi[] = ['cekirdek', 'hizmet', 'icerik', 'finans', 'analiz', 'dijital_kimlik', 'is_araclari'];

export interface AyarAlani {
  anahtar: string;
  tur: 'bool' | 'int' | 'metin' | 'secim';
  varsayilan: unknown;
  en_az?: number | null;
  en_cok?: number | null;
  secenekler?: string[];
  /** Boş (null) kabul ediliyor: boş = müşteriye özel değer yok, genel ayar geçerli. */
  bos_olabilir?: boolean;
}

/** Müşterinin kendi modülü (`/api/v1/modullerim`). */
export interface MusteriModulu {
  anahtar: string;
  ad_anahtari: string;
  aciklama_anahtari: string;
  ikon: string;
  kategori: ModulKategorisi;
  musteri_sekmesi: string | null;
  yerlesim: string[];
  durum: ModulDurumu;
  cekirdek: boolean;
  paketler: string[];
  bagimliliklar: string[];
  acik: boolean;
  kaynak: ModulKaynagi;
  gorunum: ModulGorunumu;
  ayarlar: Record<string, unknown>;
}

export interface Modullerim {
  paket: string | null;
  moduller: MusteriModulu[];
}

/** Yöneticinin gördüğü müşteri modülü (ek alanlarla). */
export interface YoneticiModulu extends MusteriModulu {
  yonetici_sekmesi: string | null;
  gerekli_rol: 'admin' | 'client' | 'her_ikisi';
  varsayilan_acik: boolean;
  acik_ham: boolean;
  elle: boolean | null;
  varsayilan_deger: boolean;
  engelleyen: string[];
  ayar_alanlari: AyarAlani[];
}

export interface MusteriModulleri {
  eposta: string;
  paket: string | null;
  moduller: YoneticiModulu[];
}

/** Manifest girdisi (`/api/v1/moduller`). */
export interface ManifestModulu {
  anahtar: string;
  ad_anahtari: string;
  aciklama_anahtari: string;
  ikon: string;
  kategori: ModulKategorisi;
  musteri_sekmesi: string | null;
  yonetici_sekmesi: string | null;
  gerekli_rol: 'admin' | 'client' | 'her_ikisi';
  varsayilan_acik: boolean;
  paketler: string[];
  bagimliliklar: string[];
  ayarlar: AyarAlani[];
  durum: ModulDurumu;
  cekirdek: boolean;
  yerlesim: string[];
}

export interface ModulOzeti {
  toplam_musteri: number;
  moduller: {
    anahtar: string;
    acik_musteri: number | null;
    elle_acik: number | null;
    elle_kapali: number | null;
  }[];
}

export interface ModulMusterisi {
  eposta: string;
  ad: string | null;
}

/** Uçtan dönen hata; `kod` sunucunun `detail.kod` değeri (ör. `bagimlilik_kapali`). */
export class ModulHatasi extends Error {
  durum: number;
  kod: string;
  moduller: string[];

  constructor(durum: number, kod: string, moduller: string[] = []) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
    this.moduller = moduller;
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
      const d = detay as { kod?: unknown; moduller?: unknown };
      throw new ModulHatasi(
        durum,
        typeof d.kod === 'string' ? d.kod : 'genel',
        Array.isArray(d.moduller) ? d.moduller.filter((x): x is string => typeof x === 'string') : []
      );
    }
    throw new ModulHatasi(durum, typeof detay === 'string' ? detay : 'genel');
  }
}

// --------------------------------------------------------------------------
// Müşteri
// --------------------------------------------------------------------------

export async function modullerimiGetir(): Promise<Modullerim> {
  const govde = await istek<Modullerim>('GET', '/api/v1/modullerim');
  if (!govde || !Array.isArray(govde.moduller)) throw new ModulHatasi(0, 'bicim');
  return { paket: govde.paket ?? null, moduller: govde.moduller };
}

// --------------------------------------------------------------------------
// Yönetici
// --------------------------------------------------------------------------

const YONETIM = '/api/v1/moduller';

export async function manifestiGetir(): Promise<ManifestModulu[]> {
  const govde = await istek<{ moduller: ManifestModulu[] }>('GET', YONETIM);
  return Array.isArray(govde?.moduller) ? govde.moduller : [];
}

export async function modulOzetiGetir(): Promise<ModulOzeti> {
  const govde = await istek<ModulOzeti>('GET', `${YONETIM}/ozet`);
  return { toplam_musteri: govde?.toplam_musteri ?? 0, moduller: govde?.moduller ?? [] };
}

export async function modulMusterileriGetir(): Promise<ModulMusterisi[]> {
  const govde = await istek<ModulMusterisi[]>('GET', `${YONETIM}/musteriler`);
  return Array.isArray(govde) ? govde : [];
}

export function musteriModulleriGetir(eposta: string): Promise<MusteriModulleri> {
  return istek<MusteriModulleri>('GET', `${YONETIM}/musteri/${encodeURIComponent(eposta)}`);
}

export function modulAyarla(
  eposta: string,
  anahtar: string,
  girdi: { acik?: boolean; ayarlar?: Record<string, unknown> }
): Promise<MusteriModulleri> {
  return istek<MusteriModulleri>(
    'PUT',
    `${YONETIM}/musteri/${encodeURIComponent(eposta)}/${encodeURIComponent(anahtar)}`,
    { ...girdi }
  );
}

export function modulVarsayilanaDon(eposta: string, anahtar: string): Promise<MusteriModulleri> {
  return istek<MusteriModulleri>(
    'DELETE',
    `${YONETIM}/musteri/${encodeURIComponent(eposta)}/${encodeURIComponent(anahtar)}`
  );
}
