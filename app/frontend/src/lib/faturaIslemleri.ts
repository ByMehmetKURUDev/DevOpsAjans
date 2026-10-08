import { formGonder, istek, kalemGirdisi, type BelgeOzeti, type Kalem } from '@/lib/belge';

/**
 * Faz 3T — fatura geliştirmeleri (mevcut `invoices` + `payments` üzerine).
 *
 * Bakiye: net borç = tutar − iade faturaları; ödenen = ödemeler − geri ödemeler;
 * kalan = net − ödenen (eksi ise müşteriye iade edilecek). Kalemli faturada
 * tutar sunucunun hesapladığı genel toplam.
 */

export type OdemeYontemi = 'havale' | 'nakit' | 'shopier' | 'lemon' | 'diger';
export const ODEME_YONTEMLERI: OdemeYontemi[] = ['havale', 'nakit', 'shopier', 'lemon', 'diger'];

export interface Bakiye {
  toplam: number;
  iade_toplam: number;
  net: number;
  odenen: number;
  kalan: number;
  fazla: number;
}

export interface FaturaOdemesi {
  id: number;
  tutar: number;
  para_birimi?: string | null;
  durum: string;
  saglayici?: string | null;
  yontem_etiketi?: string;
  odeme_tarihi?: string | null;
  odendi_at?: string | null;
  dekont_var: boolean;
  notu?: string | null;
  ekleyen_eposta?: string | null;
  jeton?: string | null;
}

export interface FaturaAyrintisi {
  id: number;
  invoice_no: string;
  client_name?: string | null;
  client_email?: string | null;
  description?: string | null;
  amount: number;
  currency: string;
  status?: string | null;
  issue_date?: string | null;
  due_date?: string | null;
  tur: string;
  bagli_fatura_id?: number | null;
  bagli_fatura_no?: string | null;
  teklif_id?: number | null;
  teklif_no?: string | null;
  tekrarlayan_id?: number | null;
  donem?: string | null;
  notlar?: string | null;
  /** Faz 5K */
  indirim_kodu?: string | null;
  kalemler: Kalem[];
  ozet: BelgeOzeti | null;
  bakiye: Bakiye | null;
  odemeler: FaturaOdemesi[];
  iadeler: { id: number; invoice_no: string; amount: number; issue_date?: string | null; description?: string | null }[];
  odeme_adresi: string | null;
}

export interface FaturaSatiri {
  id: number;
  invoice_no: string;
  description?: string | null;
  amount: number;
  currency: string;
  status?: string | null;
  issue_date?: string | null;
  due_date?: string | null;
  tur: string;
  bagli_fatura_id?: number | null;
  kalemli: boolean;
  bakiye: Bakiye | null;
  odeme_adresi: string | null;
}

export interface YaslandirmaSatiri {
  client_email: string;
  client_name?: string | null;
  para_birimi: string;
  vadesi_gelmemis: number;
  g0_30: number;
  g31_60: number;
  g61_90: number;
  g90_ustu: number;
  toplam: number;
  fatura_sayisi: number;
  en_eski_gecikme: number | null;
}

export interface Yaslandirma {
  bugun: string;
  satirlar: YaslandirmaSatiri[];
  toplamlar: ({ para_birimi: string } & Omit<YaslandirmaSatiri, 'client_email' | 'client_name' | 'para_birimi' | 'fatura_sayisi' | 'en_eski_gecikme'>)[];
}

export interface TekrarlayanSablon {
  id: number;
  client_email: string;
  client_name?: string | null;
  hizmet: string;
  baslik?: string | null;
  tutar?: number | null;
  para_birimi?: string | null;
  periyot?: string | null;
  durum?: string | null;
  fatura_otomatik: boolean;
  fatura_kalemleri: Kalem[];
  fatura_baslangic?: string | null;
  vade_gun: number;
  son_fatura_donemi?: string | null;
  fatura_sayisi?: number;
}

export interface AjansBilgileri {
  unvan: string;
  adres: string;
  vergi_dairesi: string;
  vergi_no: string;
  iban: string;
  eposta: string;
  telefon: string;
}

const YONETIM = '/api/v1/fatura-yonetim';
const MUSTERI = '/api/v1/faturalarim';

export const faturaAyrintisi = (id: number) => istek<FaturaAyrintisi>('GET', `${YONETIM}/${id}`);

export function odemeEkle(
  id: number,
  g: { tutar: string; yontem: string; tarih?: string; notu?: string; geri_odeme?: boolean; dekont?: File | null },
) {
  const f = new FormData();
  f.append('tutar', g.tutar);
  f.append('yontem', g.yontem);
  if (g.tarih) f.append('tarih', g.tarih);
  if (g.notu) f.append('notu', g.notu);
  if (g.geri_odeme) f.append('geri_odeme', '1');
  if (g.dekont) f.append('dekont', g.dekont);
  return formGonder<{ odeme_id: number; fatura: FaturaAyrintisi }>(`${YONETIM}/${id}/odemeler`, f);
}

export const odemeSil = (odemeId: number) =>
  istek<{ silindi: number; fatura?: FaturaAyrintisi }>('DELETE', `${YONETIM}/odemeler/${odemeId}`);
export const dekontAdresi = (odemeId: number) => istek<{ adres: string }>('GET', `${YONETIM}/odemeler/${odemeId}/dekont`);
export const iadeKes = (id: number, g: { tutar?: string; neden?: string }) =>
  istek<{ iade_fatura_id: number; iade_fatura_no: string; fatura: FaturaAyrintisi }>('POST', `${YONETIM}/${id}/iade`, {
    tutar: g.tutar ? g.tutar : undefined,
    neden: g.neden || undefined,
  });
export const yoneticiFaturaPdf = (id: number, dil: string) => `${YONETIM}/${id}/pdf?dil=${dil}`;
export const yaslandirma = () => istek<Yaslandirma>('GET', `${YONETIM}/yaslandirma`);
export const ajansOku = () => istek<{ kayitli: AjansBilgileri; pdf: Partial<AjansBilgileri> }>('GET', `${YONETIM}/ajans`);
export const ajansYaz = (g: Partial<AjansBilgileri>) =>
  istek<{ kayitli: AjansBilgileri; pdf: Partial<AjansBilgileri> }>('PUT', `${YONETIM}/ajans`, g);

export async function tekrarlayanListe(): Promise<TekrarlayanSablon[]> {
  const g = await istek<TekrarlayanSablon[]>('GET', `${YONETIM}/tekrarlayan`);
  return Array.isArray(g) ? g : [];
}
export const tekrarlayanEkle = (g: Partial<TekrarlayanSablon>) =>
  istek<TekrarlayanSablon>('POST', `${YONETIM}/tekrarlayan`, {
    ...g,
    fatura_kalemleri: (g.fatura_kalemleri || []).map(kalemGirdisi),
  });
export const tekrarlayanGuncelle = (id: number, g: Partial<TekrarlayanSablon>) =>
  istek<TekrarlayanSablon>('PUT', `${YONETIM}/tekrarlayan/${id}`, {
    ...g,
    ...(g.fatura_kalemleri ? { fatura_kalemleri: g.fatura_kalemleri.map(kalemGirdisi) } : {}),
  });
export const tekrarlayanCalistir = () =>
  istek<{ abonelik: number; kesilen: number; hata: number; faturalar: string[] }>('POST', `${YONETIM}/tekrarlayan/calistir`);

/** Kalemleri faturaya yazar (entity ucu; sunucu toplamı hesaplar). */
export const faturaKalemleriniYaz = (id: number, kalemler: Kalem[], indirim_kodu?: string) =>
  istek<unknown>('PUT', `/api/v1/entities/invoices/${id}`, {
    kalemler: kalemler.map(kalemGirdisi),
    // Faz 5K: "" kodu kaldırır; gönderilmezse kayıttaki kod yeni kalemlere yeniden uygulanır.
    ...(indirim_kodu !== undefined ? { indirim_kodu } : {}),
  });

// Müşteri
export async function faturalarim(): Promise<{ faturalar: FaturaSatiri[]; ozet: { para_birimi: string; kalan: number; adet: number }[] }> {
  const g = await istek<{ faturalar: FaturaSatiri[]; ozet: { para_birimi: string; kalan: number; adet: number }[] }>('GET', MUSTERI);
  return { faturalar: g?.faturalar || [], ozet: g?.ozet || [] };
}
export const faturamAyrinti = (id: number) => istek<FaturaAyrintisi>('GET', `${MUSTERI}/${id}`);
export const faturamPdf = (id: number, dil: string) => `${MUSTERI}/${id}/pdf?dil=${dil}`;
export const faturamOdemeBaglantisi = (id: number) => istek<{ adres: string; tutar: number }>('POST', `${MUSTERI}/${id}/odeme-baglantisi`);
export const faturamDekont = (id: number, odemeId: number) =>
  istek<{ adres: string }>('GET', `${MUSTERI}/${id}/odemeler/${odemeId}/dekont`);

export function faturaDurumRengi(durum?: string | null): string {
  switch (durum) {
    case 'paid':
      return 'bg-emerald-500/15 text-emerald-300';
    case 'kismi_odendi':
      return 'bg-sky-500/15 text-sky-300';
    case 'overdue':
      return 'bg-destructive/15 text-destructive';
    case 'cancelled':
    case 'iade':
      return 'bg-white/10 text-muted-foreground';
    default:
      return 'bg-orange-500/15 text-orange-300';
  }
}
