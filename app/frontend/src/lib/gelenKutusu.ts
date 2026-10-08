import { client } from '@/lib/sdkClient';

/**
 * Faz 5G — birleşik gelen kutusu uçları (yalnız yönetici).
 *
 * Bu dosyanın yalnız `sayacGetir`'i yönetim panelinin ana parçasına giriyor
 * (menü rozeti); kutunun arayüzü ayrı (lazy) parçada.
 */

export const KAYNAKLAR = [
  'iletisim',
  'fiyat_teklifi',
  'destek',
  'sohbet',
  'kartvizit',
  'randevu',
  'geri_bildirim',
  'icerik_revizyon',
  'belge',
  'egitim',
  // Faz 5B: müşterinin ajansla paylaştığı belge / paylaşılan belgeye onayı.
  'belge_paylasim',
  // Faz 6I: ajansın kendi personelinin portaldan gönderdiği izin talebi.
  'izin_talebi',
  // Faz 7K: gömülebilir CRM formu gönderimi (adaya bağlı) ve teklif kararı (bilgi öğesi).
  'crm_form',
  'teklif_karari',
] as const;
export type Kaynak = (typeof KAYNAKLAR)[number];

export type Durum = 'yeni' | 'yanit_bekliyor' | 'okundu' | 'kapandi';
export type DurumSuzgeci = 'bekleyen' | 'hepsi' | Durum;
export const DURUM_SUZGECLERI: DurumSuzgeci[] = ['bekleyen', 'hepsi', 'yeni', 'yanit_bekliyor', 'okundu', 'kapandi'];

/** Var olan bir ucu çağıran eylem; `istek` yoksa arayüzde açılır (proje formu, uzman istem). */
export interface Eylem {
  anahtar: string;
  istek: { yontem: string; yol: string; govde: Record<string, unknown> } | null;
}

export interface YanitYolu {
  tur: 'talep' | 'sohbet' | 'eposta';
  yol: string;
  alici?: string;
}

export interface Oge {
  kaynak: Kaynak;
  kimlik: number;
  anahtar: string;
  kisi_ad: string | null;
  kisi_eposta: string | null;
  baslik: string | null;
  ozet: string;
  zaman: string | null;
  durum: Durum;
  hesap_email: string | null;
  ac_baglantisi: string;
  eylemler: Eylem[];
  yanit: YanitYolu | null;
  ek: Record<string, unknown>;
}

export interface Sayac {
  toplam: number;
  kaynaklar: Partial<Record<Kaynak, number>>;
}

export interface Meta {
  ai_hazir: boolean;
  eposta_hazir: boolean;
}

export interface ListeYaniti {
  ogeler: Oge[];
  toplam: number;
  sayfa: number;
  adet: number;
  sayilar: Sayac;
  meta: Meta & { kaynaklar: Kaynak[] };
}

/** Faz 7K — gelen kutusundan giden e-posta yanıtı (öğenin yazışma geçmişi). */
export interface YanitKaydi {
  id: number;
  yazan: string | null;
  alici: string;
  konu: string | null;
  metin: string;
  durum: 'gonderildi' | 'gonderilemedi';
  neden: string | null;
  zaman: string | null;
}

export interface AyrintiYaniti {
  oge: Oge;
  ayrinti: Record<string, unknown>;
  yanitlar?: YanitKaydi[];
  meta: Meta;
}

export interface Taslak {
  taslak: string;
  dil: string;
  konu: string;
  sahte: boolean;
  marka: boolean;
}

export class GelenKutusuHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string
  ) {
    super(kod);
  }
}

function govdeyiAc<T>(yanit: unknown): T {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T;
}

/** Herhangi bir uç (öğenin eylem listesindeki var olan uçlar dahil); hata → kodlu hata. */
export async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    return govdeyiAc<T>(await client.apiCall.invoke({ method, url, data }));
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    const durum = h?.response?.status ?? h?.status ?? 0;
    const detay = h?.response?.data?.detail;
    const kod =
      detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string'
        ? (detay as { kod: string }).kod
        : 'genel';
    throw new GelenKutusuHatasi(durum, kod);
  }
}

const TABAN = '/api/v1/gelen-kutusu';

export const sayacGetir = () => istek<Sayac>('GET', `${TABAN}/sayac`);

export function listeGetir(p: {
  kaynak?: Kaynak | null;
  durum: DurumSuzgeci;
  q?: string;
  bas?: string;
  bit?: string;
  sayfa?: number;
  adet?: number;
}): Promise<ListeYaniti> {
  const s = new URLSearchParams();
  if (p.kaynak) s.set('kaynak', p.kaynak);
  s.set('durum', p.durum);
  if (p.q?.trim()) s.set('q', p.q.trim());
  if (p.bas) s.set('bas', p.bas);
  if (p.bit) s.set('bit', p.bit);
  if (p.sayfa) s.set('sayfa', String(p.sayfa));
  if (p.adet) s.set('adet', String(p.adet));
  return istek<ListeYaniti>('GET', `${TABAN}?${s.toString()}`);
}

export const ayrintiGetir = (kaynak: Kaynak, kimlik: number) =>
  istek<AyrintiYaniti>('GET', `${TABAN}/${kaynak}/${kimlik}`);

export const taslakUret = (kaynak: Kaynak, kimlik: number, girdi: { dil?: string | null; talimat?: string }) =>
  istek<Taslak>('POST', `${TABAN}/${kaynak}/${kimlik}/taslak`, girdi as Record<string, unknown>);

export const epostaGonder = (kaynak: Kaynak, kimlik: number, girdi: { konu: string; metin: string }) =>
  istek<{ gonderildi: boolean; oge: Oge }>('POST', `${TABAN}/${kaynak}/${kimlik}/eposta`, girdi);

/** Öğenin eylem listesindeki var olan ucu olduğu gibi çağırır. */
export function eylemiCalistir(e: Eylem): Promise<unknown> {
  if (!e.istek) return Promise.resolve(null);
  return istek(e.istek.yontem, e.istek.yol, e.istek.govde);
}
