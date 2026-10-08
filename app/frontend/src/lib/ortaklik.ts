import { acikIstek, BelgeHatasi, formGonder, istek, pdfIndir } from '@/lib/belge';

/**
 * Faz 5K — ortaklık (referans) programı uçları.
 *
 * * Herkese açık `/api/v1/ortaklik`: program bilgisi, başvuru.
 * * Ortak `/api/v1/ortakligim`: kişiye ait panel, IBAN, ödeme talebi, dekont; girişten sonra kayıt referansı.
 * * Yönetici `/api/v1/ortaklik-yonetim`: ortaklar, başvuru kararı, komisyonlar, ödeme talepleri, CSV, ayarlar.
 */

export type ParaBirimi = 'TRY' | 'USD' | 'EUR' | 'GBP';
export type OrtakDurumu = 'beklemede' | 'onaylandi' | 'reddedildi' | 'askida';
export type KomisyonDurumu = 'beklemede' | 'onaylandi' | 'odeme_talebinde' | 'odendi' | 'iptal';
export type TalepDurumu = 'bekliyor' | 'odendi' | 'reddedildi';

export interface ProgramBilgisi {
  acik: boolean;
  varsayilan_oran: number;
  /** Tekrar eden (abonelik) faturalarında oran ve ilk satıştan sonraki süre (ay; 0 = kapalı). */
  tekrar_oran: number;
  tekrar_ay: number;
  bekleme_gun: number;
  odeme_en_az: Record<string, number>;
  cerez_gun: number;
  kosullar: string | null;
  kosullar_surumu: string;
}

export interface Bakiye {
  kazanc: number;
  beklemede: number;
  onaylandi: number;
  odeme_talebinde: number;
  odendi: number;
}

export interface Ortak {
  id: number;
  ad: string;
  eposta: string;
  web: string | null;
  kod: string | null;
  durum: OrtakDurumu;
  oran: number;
  oran_ozel: boolean;
  iban: string | null;
  iban_ad: string | null;
  baglanti: string | null;
  basvuru_at: string | null;
  karar_at: string | null;
  // yönetici
  tanitim?: string | null;
  notlar?: string | null;
  ret_nedeni?: string | null;
  supheli?: string[];
  dil?: string | null;
  kosullar_kabul_at?: string | null;
  kosullar_surumu?: string | null;
  pazarlama_izni?: boolean;
  iban_tam?: string | null;
  bakiyeler?: Record<string, Bakiye>;
  tiklama?: number;
  aday?: number;
}

export interface Komisyon {
  id: number;
  tur: 'komisyon' | 'ters';
  /** ilk: ilk satış (oran X); tekrar: N ay içindeki abonelik faturası (oran Y). */
  kural: 'ilk' | 'tekrar';
  fatura_no: string | null;
  matrah: number;
  oran: number;
  tutar: number;
  para_birimi: string;
  durum: KomisyonDurumu;
  bekleme_bitis: string | null;
  odeme_talebi_id: number | null;
  notu: string | null;
  created_at: string | null;
  musteri: string | null;
  // yönetici
  ortak_id?: number;
  ortak_ad?: string | null;
  fatura_id?: number | null;
  musteri_eposta?: string | null;
  supheli?: string[];
}

export interface OdemeTalebi {
  id: number;
  tutar: number;
  para_birimi: string;
  durum: TalepDurumu;
  iban: string | null;
  notu: string | null;
  ret_nedeni: string | null;
  dekont_var: boolean;
  odendi_at: string | null;
  created_at: string | null;
  ortak_id?: number;
  iban_ad?: string | null;
  ortak_ad?: string | null;
  ortak_eposta?: string | null;
}

export interface OrtakPaneli {
  durum: OrtakDurumu | null;
  ortak?: Ortak;
  tiklama?: { son_gun: number; son_toplam: number; toplam: number; gunler: { gun: string; sayi: number }[] };
  aday?: number;
  satis?: number;
  bakiyeler?: Record<string, Bakiye>;
  komisyonlar?: Komisyon[];
  talepler?: OdemeTalebi[];
  program?: ProgramBilgisi;
}

export interface ProgramAyarlari {
  acik: boolean;
  varsayilan_oran: number;
  tekrar_oran: number;
  tekrar_ay: number;
  bekleme_gun: number;
  odeme_en_az: Record<string, number>;
  atif: 'ilk' | 'son';
  tum_faturalar: boolean;
  kosullar: Record<string, string>;
}

export interface BasvuruGirdisi {
  ad: string;
  eposta: string;
  web: string;
  tanitim: string;
  kosullar_kabul: boolean;
  pazarlama_izni: boolean;
  dil: string;
  web_sitesi?: string;
}

const ACIK = '/api/v1/ortaklik';
const BEN = '/api/v1/ortakligim';
const YON = '/api/v1/ortaklik-yonetim';

export { BelgeHatasi };

// Herkese açık
export const programBilgisi = (dil: string) => acikIstek<ProgramBilgisi>('GET', `${ACIK}/program?dil=${encodeURIComponent(dil)}`);
export const basvur = (g: BasvuruGirdisi) => acikIstek<{ ok: boolean }>('POST', `${ACIK}/basvuru`, g);

// Ortak
export const ortaklikDurumum = () => istek<{ durum: OrtakDurumu | null }>('GET', `${BEN}/durum`);
export const ortakPanelim = () => istek<OrtakPaneli>('GET', BEN);
export const ibanKaydet = (iban: string, iban_ad: string) => istek<{ iban: string; iban_ad: string }>('PUT', `${BEN}/iban`, { iban, iban_ad });
export const odemeIste = (para_birimi: string) => istek<OdemeTalebi>('POST', `${BEN}/odeme-talebi`, { para_birimi });
export const dekontumAdresi = (id: number) => istek<{ adres: string }>('GET', `${BEN}/odeme-talepleri/${id}/dekont`);
/** Kayıt sonrası referans: bağlantıdan gelen kod girişten sonra bir kez (sunucu yalnız yeni açılmış hesapta atar). */
export const kayitReferansi = (kod: string) => istek<{ atif: boolean }>('POST', `${BEN}/kayit-referansi`, { kod });

// Yönetici
export const yonetimOzeti = () =>
  istek<{ bekleyen_basvuru: number; ortak: number; bekleyen_talep: number; supheli_komisyon: number }>('GET', `${YON}/ozet`);
export async function ortakListesi(durum?: string): Promise<Ortak[]> {
  const g = await istek<Ortak[]>('GET', durum ? `${YON}/ortaklar?durum=${durum}` : `${YON}/ortaklar`);
  return Array.isArray(g) ? g : [];
}
export const ortakKarar = (id: number, g: { karar: 'onay' | 'ret'; oran?: string; kod?: string; neden?: string }) =>
  istek<Ortak>('POST', `${YON}/ortaklar/${id}/karar`, g);
export const ortakGuncelle = (id: number, g: Record<string, unknown>) => istek<Ortak>('PATCH', `${YON}/ortaklar/${id}`, g);
export async function komisyonListesi(durum?: string): Promise<Komisyon[]> {
  const g = await istek<Komisyon[]>('GET', durum ? `${YON}/komisyonlar?durum=${durum}` : `${YON}/komisyonlar`);
  return Array.isArray(g) ? g : [];
}
export const komisyonIslem = (id: number, islem: 'onayla' | 'iptal', not?: string) =>
  istek<Komisyon>('POST', `${YON}/komisyonlar/${id}/islem`, { islem, not });
export async function talepListesi(durum?: string): Promise<OdemeTalebi[]> {
  const g = await istek<OdemeTalebi[]>('GET', durum ? `${YON}/odeme-talepleri?durum=${durum}` : `${YON}/odeme-talepleri`);
  return Array.isArray(g) ? g : [];
}
export function talepOdendi(id: number, notu: string, dekont: File | null) {
  const form = new FormData();
  if (notu) form.append('notu', notu);
  if (dekont) form.append('dekont', dekont);
  return formGonder<OdemeTalebi>(`${YON}/odeme-talepleri/${id}/odendi`, form);
}
export const talepReddet = (id: number, neden: string) => istek<OdemeTalebi>('POST', `${YON}/odeme-talepleri/${id}/reddet`, { neden });
export const talepDekontu = (id: number) => istek<{ adres: string }>('GET', `${YON}/odeme-talepleri/${id}/dekont`);
/** CSV (muhasebe): komisyon defteri ve ödeme talepleri (IBAN maskeli); süzgeç listedekiyle aynı. */
export const komisyonCsv = (durum?: string) =>
  pdfIndir(durum ? `${YON}/komisyonlar.csv?durum=${encodeURIComponent(durum)}` : `${YON}/komisyonlar.csv`, 'ortaklik-komisyonlar.csv');
export const talepCsv = (durum?: string) =>
  pdfIndir(durum ? `${YON}/odeme-talepleri.csv?durum=${encodeURIComponent(durum)}` : `${YON}/odeme-talepleri.csv`, 'ortaklik-odeme-talepleri.csv');
export const ayarlariGetir = () => istek<ProgramAyarlari>('GET', `${YON}/ayarlar`);
export const ayarlariKaydet = (g: Partial<ProgramAyarlari>) => istek<ProgramAyarlari>('PUT', `${YON}/ayarlar`, g);

/** Hata kodu → ek paketteki metin (yoksa genel). */
export function hataMetni(t: (k: string, o?: Record<string, unknown>) => string, h: unknown, on: string): string {
  if (h instanceof BelgeHatasi) {
    const anahtar = `${on}.${h.kod}`;
    const metin = t(anahtar, { ...h.ek, defaultValue: '' });
    if (metin) return metin;
  }
  return t(`${on}.genel`);
}
