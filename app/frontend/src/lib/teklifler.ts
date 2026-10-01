import { acikIstek, istek, kalemGirdisi, type BelgeOzeti, type Kalem } from '@/lib/belge';

/**
 * Faz 3T — teklif (öneri) uçları.
 *
 * * Yönetici `/api/v1/teklif-yonetim`: CRUD, gönder (bağlantı yalnız bu
 *   yanıtta, bir kez), revize, PDF, fiyat sihirbazından teklife çevir.
 * * Girişsiz `/api/v1/teklif/<jeton>`: görüntüle (sayaç artar), karar, PDF.
 * * Müşteri `/api/v1/tekliflerim` (`faturalar` izni).
 */

export type TeklifDurumu = 'taslak' | 'gonderildi' | 'goruntulendi' | 'kabul' | 'ret' | 'suresi_doldu' | 'revize';
export const TEKLIF_DURUMLARI: TeklifDurumu[] = ['taslak', 'gonderildi', 'goruntulendi', 'kabul', 'ret', 'suresi_doldu', 'revize'];

export interface Teklif {
  id: number;
  no: string;
  baslik: string;
  kalemler: Kalem[];
  ozet: BelgeOzeti;
  para_birimi: string;
  gecerlilik: string | null;
  notlar: string | null;
  sartlar: string | null;
  durum: TeklifDurumu | string;
  surum: number;
  musteri_ad: string | null;
  karar_at: string | null;
  karar_ad: string | null;
  karar_notu: string | null;
  fatura_id?: number | null;
  sozlesme_id?: number | null;
  proje_id?: number | null;
  tarih: string;
  // yönetici
  hesap_email?: string | null;
  aday_eposta?: string | null;
  goruntulenme_sayisi?: number;
  ilk_goruntulenme?: string | null;
  son_goruntulenme?: string | null;
  gonderildi_at?: string | null;
  karar_ip_ozeti?: string | null;
  otomatik_sozlesme?: boolean;
  sozlesme_sablon_id?: number | null;
  otomatik_fatura?: boolean;
  pesinat_yuzde?: number | null;
  otomatik_proje?: boolean;
  pricing_inquiry_id?: number | null;
  onceki_id?: number | null;
  // girişsiz / müşteri
  karar_verilebilir?: boolean;
  baglanti_durumu?: string;
  alici?: string;
  son_kullanma?: string | null;
}

export interface TeklifGirdisi {
  baslik?: string;
  kalemler?: Kalem[];
  para_birimi?: string;
  hesap_email?: string;
  aday_ad?: string;
  aday_eposta?: string;
  gecerlilik?: string;
  notlar?: string;
  sartlar?: string;
  otomatik_sozlesme?: boolean;
  sozlesme_sablon_id?: number | null;
  otomatik_fatura?: boolean;
  pesinat_yuzde?: number | string | null;
  otomatik_proje?: boolean;
}

export interface FiyatTalebi {
  id: number;
  musteri_eposta: string;
  musteri_adi?: string | null;
  tutar: number;
  period?: string | null;
  scale_kod?: string | null;
  ai_pm_tier_kod?: string | null;
  invoice_id?: number | null;
  durum?: string | null;
  teklif?: { id: number; no: string; durum: string } | null;
}

const YONETIM = '/api/v1/teklif-yonetim';
const ACIK = '/api/v1/teklif';
const MUSTERI = '/api/v1/tekliflerim';

function girdi(g: TeklifGirdisi): Record<string, unknown> {
  const veri: Record<string, unknown> = { ...g };
  if (g.kalemler) veri.kalemler = g.kalemler.map(kalemGirdisi);
  if (g.pesinat_yuzde === '') veri.pesinat_yuzde = null;
  return veri;
}

export async function teklifListesi(filtre: { durum?: string; q?: string } = {}): Promise<Teklif[]> {
  const s = new URLSearchParams();
  if (filtre.durum) s.set('durum', filtre.durum);
  if (filtre.q) s.set('q', filtre.q);
  const q = s.toString();
  const govde = await istek<Teklif[]>('GET', q ? `${YONETIM}?${q}` : YONETIM);
  return Array.isArray(govde) ? govde : [];
}

export const teklifOlustur = (g: TeklifGirdisi) => istek<Teklif>('POST', YONETIM, girdi(g));
export const teklifGuncelle = (id: number, g: TeklifGirdisi) => istek<Teklif>('PUT', `${YONETIM}/${id}`, girdi(g));
export const teklifSil = (id: number) => istek<{ silindi: number }>('DELETE', `${YONETIM}/${id}`);
export const teklifGonder = (id: number, eposta_gonder: boolean) =>
  istek<{ teklif: Teklif; baglanti: string; eposta_gonderildi: boolean }>('POST', `${YONETIM}/${id}/gonder`, { eposta_gonder });
export const teklifRevize = (id: number) => istek<Teklif>('POST', `${YONETIM}/${id}/revize`);
export const fiyatTalepleri = async () => {
  const g = await istek<FiyatTalebi[]>('GET', `${YONETIM}/fiyat-talepleri`);
  return Array.isArray(g) ? g : [];
};
export const fiyatTalebindenTeklif = (id: number) => istek<Teklif>('POST', `${YONETIM}/fiyat-talebinden/${id}`);
export const yoneticiTeklifPdf = (id: number, dil: string) => `${YONETIM}/${id}/pdf?dil=${dil}`;

// Girişsiz
export const acikTeklif = (jeton: string) => acikIstek<Teklif>('GET', `${ACIK}/${encodeURIComponent(jeton)}`);
export const acikTeklifKarar = (jeton: string, g: { sonuc: 'kabul' | 'red'; ad_soyad?: string; not?: string }) =>
  acikIstek<Teklif>('POST', `${ACIK}/${encodeURIComponent(jeton)}/karar`, g);
export const acikTeklifPdf = (jeton: string, dil: string) => `${ACIK}/${encodeURIComponent(jeton)}/pdf?dil=${dil}`;

// Müşteri
export async function tekliflerim(): Promise<Teklif[]> {
  const g = await istek<Teklif[]>('GET', MUSTERI);
  return Array.isArray(g) ? g : [];
}
export const teklifimKarar = (id: number, g: { sonuc: 'kabul' | 'red'; ad_soyad?: string; not?: string }) =>
  istek<Teklif>('POST', `${MUSTERI}/${id}/karar`, g);
export const teklifimPdf = (id: number, dil: string) => `${MUSTERI}/${id}/pdf?dil=${dil}`;

export function teklifDurumRengi(durum: string): string {
  switch (durum) {
    case 'kabul':
      return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300';
    case 'ret':
      return 'border-red-400/30 bg-red-500/10 text-red-300';
    case 'gonderildi':
    case 'goruntulendi':
      return 'border-sky-400/30 bg-sky-500/10 text-sky-300';
    case 'suresi_doldu':
    case 'revize':
      return 'border-amber-400/30 bg-amber-500/10 text-amber-300';
    default:
      return 'border-white/15 bg-white/5 text-muted-foreground';
  }
}
