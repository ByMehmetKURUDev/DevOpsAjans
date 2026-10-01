import { client } from '@/lib/sdkClient';
import { pdfIndir } from '@/lib/belge';

/**
 * Faz 3Z — zaman takibi + proje şablonları.
 *
 * Personel + yönetici  /api/v1/zaman/...          (personel yalnız kendi kayıtları)
 * Yönetici             /api/v1/zaman/yonetim/..., /api/v1/proje-sablonlari
 * Müşteri              /api/v1/zamanim/proje/{id} (harcanan süre özeti)
 */

export type ZamanDurumu = 'taslak' | 'onaylandi' | 'reddedildi' | 'faturalandi';
export const ZAMAN_DURUMLARI: ZamanDurumu[] = ['taslak', 'onaylandi', 'reddedildi', 'faturalandi'];
export type ZamanTuru = 'normal' | 'revizyon';
export type Gruplama = 'tek' | 'kisi' | 'gorev';
export const PARA_BIRIMLERI = ['TRY', 'USD', 'EUR', 'GBP'] as const;

export interface ZamanKaydi {
  id: number;
  proje_id: number;
  proje_baslik: string | null;
  gorev_id: number | null;
  gorev_baslik: string | null;
  kisi_eposta: string;
  kisi_ad: string | null;
  baslangic: string;
  bitis: string | null;
  gun: string | null;
  sure_dk: number | null;
  calisiyor: boolean;
  gecen_dk: number | null;
  uzun: boolean;
  aciklama: string | null;
  faturalanabilir: boolean;
  saatlik_ucret: number | null;
  para_birimi: string | null;
  tutar: number | null;
  tur: ZamanTuru;
  durum: ZamanDurumu;
  kilitli: boolean;
  ret_notu: string | null;
  onaylayan_eposta: string | null;
  onay_at: string | null;
  fatura_id: number | null;
  created_at: string | null;
}

export interface Secenekler {
  projeler: { id: number; baslik: string; client_email?: string | null; durum?: string | null }[];
  gorevler: { id: number; proje_id: number; baslik: string; atanan: string | null; revizyon: boolean }[];
  ekip?: { ad: string; email: string }[];
  ayarlar?: { saatlik_ucret: number | null; para_birimi: string };
  uzun_sayac_dk: number;
  en_cok_sure_dk: number;
}

export interface Ben {
  eposta: string;
  yonetici: boolean;
  personel: boolean;
  ad: string | null;
}

export interface Cizelge {
  hafta_baslangic: string;
  gunler: string[];
  kisiler: {
    eposta: string;
    ad: string | null;
    gunler: number[];
    toplam_dk: number;
    onayli_dk: number;
    taslak_dk: number;
    faturalanabilir_dk: number;
  }[];
  gun_toplamlari: number[];
  genel_toplam_dk: number;
}

export interface IsYuku {
  bugun: string;
  bu_hafta_baslangic: string;
  gecen_hafta_baslangic: string;
  kisiler: {
    eposta: string;
    ad: string | null;
    bu_hafta_dk: number;
    gecen_hafta_dk: number;
    acik_gorev: number;
    geciken_gorev: number;
  }[];
  en_cok_dk: number;
  en_cok_gorev: number;
}

export interface Faturalanabilir {
  proje: { id: number; baslik: string; client_email: string | null };
  kayitlar: ZamanKaydi[];
  toplam_dk: number;
  proje_ucreti: number | null;
  para_birimi: string;
  ucret_kaynagi: 'proje' | 'site' | 'yok';
}

export interface AktarimSonucu {
  fatura_id: number;
  invoice_no: string;
  yeni_fatura: boolean;
  durum: string;
  tutar: number;
  para_birimi: string;
  kalem_sayisi: number;
  kayit_sayisi: number;
  kayitlar: number[];
}

export interface ProjeAyari {
  proje_id: number;
  saatlik_ucret: number | null;
  ucret_para_birimi: string | null;
  sure_musteriye_gorunur: boolean;
  faturalanabilir_musteriye_gorunur: boolean;
  etkin_ucret: number | null;
  etkin_para_birimi: string;
  ucret_kaynagi: 'proje' | 'site' | 'yok';
}

export interface MusteriSureOzeti {
  proje_id: number;
  toplam_dk: number;
  toplam_saat: number;
  bu_ay_dk: number;
  kayit_sayisi: number;
  son_kayit: string | null;
  faturalanabilir_dk?: number;
  faturalanabilir_saat?: number;
}

export interface SablonGorevi {
  baslik: string;
  aciklama?: string | null;
  asama?: string | null;
  baslangic_gun: number;
  sure_gun: number;
  kontrol_listesi: string[];
  atanan_eposta?: string | null;
  atanan_rol?: string | null;
  musteriye_gorunur: boolean;
  kilometre_tasi: boolean;
  oncelik?: string;
  tahmini_saat?: number | null;
}

export interface ProjeSablonu {
  id: number;
  ad: string;
  aciklama: string | null;
  kategori: string | null;
  tahmini_saat: number | null;
  gorevler: SablonGorevi[];
  gorev_sayisi: number;
  toplam_gun: number;
  hazir: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface SablondanProje {
  proje: { id: number; baslik: string; client_email: string | null };
  gorev_sayisi: number;
  gorevler: { id: number; baslik: string; baslangic_tarihi: string | null; bitis_tarihi: string | null; atanan: string | null; musteriye_gorunur: boolean }[];
}

/** Uçtan dönen hata; `kod` sunucunun `detail.kod`u, `ek` diğer alanlar. */
export class ZamanHatasi extends Error {
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
      const { kod, ...ek } = detay as Record<string, unknown>;
      throw new ZamanHatasi(durum, typeof kod === 'string' ? kod : 'genel', ek);
    }
    throw new ZamanHatasi(durum, 'genel');
  }
}

function sorgu(p: Record<string, string | number | boolean | null | undefined>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v));
  const metin = s.toString();
  return metin ? `?${metin}` : '';
}

// --- Biçim ---------------------------------------------------------------------
/** 95 → "1:35" */
export function sureGoster(dk: number | null | undefined): string {
  const d = Math.max(0, Math.round(dk || 0));
  return `${Math.floor(d / 60)}:${String(d % 60).padStart(2, '0')}`;
}

/** Saniye cinsinden geçen süre → "01:02:03" (sayaç çubuğu). */
export function saniyeGoster(sn: number): string {
  const s = Math.max(0, Math.floor(sn));
  return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60].map((x) => String(x).padStart(2, '0')).join(':');
}

/** "1:30", "1.5", "90m", "90" (dakika) → dakika; geçersiz → null. */
export function sureCoz(metin: string): number | null {
  const m = metin.trim().toLowerCase().replace(',', '.');
  if (!m) return null;
  let dk: number;
  if (/^\d{1,2}:\d{1,2}$/.test(m)) {
    const [s, d] = m.split(':').map(Number);
    dk = s * 60 + d;
  } else if (/^\d+(\.\d+)?h$/.test(m) || /^\d+\.\d+$/.test(m)) {
    dk = Math.round(parseFloat(m) * 60);
  } else if (/^\d+m?$/.test(m)) {
    dk = parseInt(m, 10);
  } else return null;
  return dk >= 1 ? dk : null;
}

export function bugunYerel(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function gunEkle(gun: string, n: number): string {
  const [y, a, g] = gun.split('-').map(Number);
  const d = new Date(Date.UTC(y, a - 1, g + n));
  return d.toISOString().slice(0, 10);
}

export function paraGoster(tutar: number | null | undefined, pb: string | null | undefined, dil: string): string {
  if (tutar === null || tutar === undefined) return '—';
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: pb || 'TRY' }).format(tutar);
  } catch {
    return `${tutar.toFixed(2)} ${pb || ''}`.trim();
  }
}

export function tarihGoster(gun: string | null | undefined, dil: string): string {
  if (!gun) return '';
  try {
    return new Date(`${gun.slice(0, 10)}T12:00:00`).toLocaleDateString(dil, { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return gun.slice(0, 10);
  }
}

export function gunAdi(gun: string, dil: string): string {
  try {
    return new Date(`${gun}T12:00:00`).toLocaleDateString(dil, { weekday: 'short', day: 'numeric', month: 'short' });
  } catch {
    return gun;
  }
}

// --- Personel + yönetici --------------------------------------------------------
const Z = '/api/v1/zaman';
const ZY = '/api/v1/zaman/yonetim';

export const zamanBen = () => istek<Ben>('GET', `${Z}/ben`);
export const secenekleriGetir = () => istek<Secenekler>('GET', `${Z}/secenekler`);
export const sayacGetir = () => istek<{ sayac: ZamanKaydi | null; uzun_sayac_dk: number }>('GET', `${Z}/sayac`);
export const sayacBaslat = (girdi: { proje_id: number; gorev_id?: number | null; aciklama?: string; faturalanabilir?: boolean; tur?: ZamanTuru }) =>
  istek<{ sayac: ZamanKaydi; durdurulan: ZamanKaydi | null }>('POST', `${Z}/sayac/baslat`, girdi);
export const sayacDurdur = (girdi: { sure_dk?: number; aciklama?: string } = {}) =>
  istek<{ kayit: ZamanKaydi }>('POST', `${Z}/sayac/durdur`, girdi);

export interface KayitSuzgeci {
  durum?: string;
  proje_id?: number | null;
  kisi?: string;
  baslangic?: string;
  bitis?: string;
  faturalanabilir?: boolean;
  sinir?: number;
}

export async function kayitlariGetir(s: KayitSuzgeci = {}): Promise<ZamanKaydi[]> {
  const y = await istek<{ kayitlar: ZamanKaydi[] }>('GET', `${Z}/kayitlar${sorgu({ ...s })}`);
  return y?.kayitlar ?? [];
}

export type KayitGirdisi = Partial<{
  proje_id: number;
  gorev_id: number | null;
  tarih: string;
  saat: string;
  sure_dk: number;
  aciklama: string;
  faturalanabilir: boolean;
  tur: ZamanTuru;
  kisi_eposta: string;
}>;

export const kayitEkle = (g: KayitGirdisi) => istek<ZamanKaydi>('POST', `${Z}/kayitlar`, g as Record<string, unknown>);
export const kayitGuncelle = (id: number, g: KayitGirdisi) => istek<ZamanKaydi>('PATCH', `${Z}/kayitlar/${id}`, g as Record<string, unknown>);
export const kayitSil = (id: number) => istek<{ silindi: number }>('DELETE', `${Z}/kayitlar/${id}`);
export const cizelgeGetir = (hafta?: string, kisi?: string) => istek<Cizelge>('GET', `${Z}/cizelge${sorgu({ hafta, kisi })}`);

// --- Yönetici -------------------------------------------------------------------
export const onayIslemi = (idler: number[], islem: 'onayla' | 'reddet', not?: string) =>
  istek<{ islem: string; islenen: number[]; atlanan: number[] }>('POST', `${ZY}/onay`, { idler, islem, not });
export const onayiGeriAl = (id: number) => istek<ZamanKaydi>('POST', `${ZY}/kayitlar/${id}/onay-geri-al`);
export const isYukuGetir = () => istek<IsYuku>('GET', `${ZY}/is-yuku`);
export const faturalanabilirGetir = (projeId: number) => istek<Faturalanabilir>('GET', `${ZY}/faturalanabilir${sorgu({ proje_id: projeId })}`);
export const faturayaAktar = (g: {
  proje_id: number;
  idler?: number[];
  gruplama: Gruplama;
  kdv_orani: number;
  varsayilan_ucret?: number | null;
}) => istek<AktarimSonucu>('POST', `${ZY}/faturaya-aktar`, g as Record<string, unknown>);
export const projeAyariGetir = (projeId: number) => istek<ProjeAyari>('GET', `${ZY}/proje/${projeId}/ayar`);
export const projeAyariYaz = (projeId: number, g: Partial<ProjeAyari>) =>
  istek<ProjeAyari>('PUT', `${ZY}/proje/${projeId}/ayar`, g as Record<string, unknown>);
export const zamanAyarlari = () => istek<{ saatlik_ucret: number | null; para_birimi: string }>('GET', `${ZY}/ayarlar`);
export const zamanAyarlariYaz = (g: { saatlik_ucret: number | null; para_birimi: string }) =>
  istek<{ saatlik_ucret: number | null; para_birimi: string }>('PUT', `${ZY}/ayarlar`, g);

export function csvIndir(s: { baslangic?: string; bitis?: string; proje_id?: number | null }): Promise<void> {
  return pdfIndir(`${ZY}/disa-aktar.csv${sorgu(s)}`, `zaman-${s.baslangic || 'tum'}-${s.bitis || bugunYerel()}.csv`);
}

// --- Müşteri --------------------------------------------------------------------
export const musteriSuresi = (projeId: number) => istek<MusteriSureOzeti>('GET', `/api/v1/zamanim/proje/${projeId}`);

// --- Proje şablonları -------------------------------------------------------------
const S = '/api/v1/proje-sablonlari';

export async function sablonlariGetir(): Promise<ProjeSablonu[]> {
  const y = await istek<{ sablonlar: ProjeSablonu[] }>('GET', S);
  return y?.sablonlar ?? [];
}

export type SablonGirdisi = { ad: string; aciklama?: string | null; kategori?: string | null; tahmini_saat?: number | null; gorevler: SablonGorevi[] };

export const sablonEkle = (g: SablonGirdisi) => istek<ProjeSablonu>('POST', S, g as unknown as Record<string, unknown>);
export const sablonGuncelle = (id: number, g: Partial<SablonGirdisi>) => istek<ProjeSablonu>('PUT', `${S}/${id}`, g as unknown as Record<string, unknown>);
export const sablonSil = (id: number) => istek<{ silindi: number }>('DELETE', `${S}/${id}`);
export const sablondanProje = (
  id: number,
  g: { baslangic_tarihi: string; baslik?: string; client_email?: string; client_name?: string },
) => istek<SablondanProje>('POST', `${S}/${id}/proje-olustur`, g);
export const projedenSablon = (projeId: number, ad?: string) => istek<ProjeSablonu>('POST', `${S}/projeden/${projeId}`, { ad });
