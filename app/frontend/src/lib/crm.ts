import type { TFunction } from 'i18next';

import { client } from '@/lib/sdkClient';

/**
 * Faz 3C — CRM ve aday hunisi (yalnız yönetici).
 *
 * Uç ayrıntısı: `app/backend/routers/crm.py`. Hata gövdesi
 * `{detail: {kod, ...}}` → `CrmHatasi(kod)`; metin `crm.hata.<kod>` (ek paket, 7 dil).
 */

export type AsamaTuru = 'acik' | 'kazanildi' | 'kaybedildi';
export type Kaynak =
  | 'iletisim'
  | 'bekleme'
  | 'site_analizi'
  | 'kesif'
  | 'fiyat_teklifi'
  | 'kaynaklar'
  | 'form'
  | 'manuel'
  | 'eposta';
export type ElleAktivite = 'not' | 'arama' | 'eposta' | 'toplanti';

export interface Asama {
  anahtar: string;
  ad: string;
  ceviriler: Record<string, { ad?: string }>;
  sira: number;
  renk: string;
  tur: AsamaTuru;
  olasilik: number | null;
  aday_sayisi?: number;
}

export interface Aday {
  id: number;
  ad: string;
  firma: string | null;
  email: string | null;
  telefon: string | null;
  kaynak: Kaynak;
  kaynak_detay: string | null;
  asama: string;
  deger_tahmini: number | null;
  para_birimi: string;
  olasilik: number | null;
  sorumlu: string | null;
  etiketler: string[];
  sonraki_adim: string | null;
  sonraki_adim_tarihi: string | null;
  gecikti: boolean;
  bugun: boolean;
  musteri_email: string | null;
  puan: number;
  created_at: string | null;
  updated_at: string | null;
  asama_degisme_at: string | null;
}

export interface PuanSatiri {
  kural: 'kaynak' | 'butce' | 'kapsam' | 'alan_adi' | 'etkilesim';
  puan: number;
  en_cok: number;
  deger: string | number | boolean;
}

export interface AdayAyrintisi extends Aday {
  notlar: string | null;
  ilk_mesaj: string | null;
  butce: string | null;
  kaybedilme_nedeni: string | null;
  puan_ayrinti: PuanSatiri[];
  kaynak_tablo: string | null;
  kaynak_id: number | null;
  /** Faz 4G: pazarlama (ticari ileti) izni — en son verildiği an, kaynağı ("form:3" | "site_analizi:12"), metin sürümü ("1/tr"). */
  pazarlama_izni?: boolean;
  pazarlama_izni_at?: string | null;
  pazarlama_izni_kaynak?: string | null;
  pazarlama_metin_surumu?: string | null;
}

export interface Aktivite {
  id: number;
  aday_id: number;
  tur: ElleAktivite | 'asama' | 'sistem';
  olay: string | null;
  veri: Record<string, unknown>;
  metin: string | null;
  yapan: string | null;
  zaman: string | null;
}

export interface BagliKayit {
  tablo: 'inquiries' | 'pricing_inquiries' | 'crm_form_gonderimleri';
  kayit_id: number;
  silinmis?: boolean;
  baslik?: string;
  kaynak?: string | null;
  durum?: string | null;
  tutar?: number;
  para_birimi?: string;
  form_id?: number;
  kvkk_surum?: number;
  kvkk_onay_at?: string | null;
  koken?: string | null;
  /** Faz 4G: bu gönderimde isteğe bağlı pazarlama izni verildi mi. */
  pazarlama_izni?: boolean;
  pazarlama_izni_at?: string | null;
  pazarlama_metin_surumu?: string | null;
  zaman?: string | null;
}

export interface Sorumlu {
  email: string;
  ad: string | null;
  rol: string;
}

export interface CrmMeta {
  asamalar: Asama[];
  sorumlular: Sorumlu[];
  kaynaklar: Kaynak[];
  aktivite_turleri: ElleAktivite[];
  para_birimleri: string[];
  renkler: string[];
  siralamalar: string[];
}

export interface KanbanSutunu extends Asama {
  sayi: number;
  toplam_deger: Record<string, number>;
  adaylar: Aday[];
}

export interface Ozet {
  toplam: number;
  acik: number;
  kazanilan: number;
  kaybedilen: number;
  geciken: number;
  huni: { anahtar: string; ulasan: number; simdi: number; donusum: number | null }[];
  kaynaklar: { kaynak: Kaynak; sayi: number; kazanilan: number; kaybedilen: number; kazanma_orani: number }[];
  asama_sureleri: { anahtar: string; ortalama_gun: number; ornek: number }[];
  bu_ay: { kazanilan_sayi: number; deger: Record<string, number>; ay: string };
  acik_deger: Record<string, number>;
}

export type FormAlani = 'ad' | 'email' | 'telefon' | 'firma' | 'mesaj' | 'butce';

export interface CrmFormu {
  id: number;
  ad: string;
  baslik: string | null;
  genel_anahtar: string;
  alanlar: Record<FormAlani, { acik: boolean; zorunlu: boolean }>;
  varsayilan_asama: string | null;
  varsayilan_etiketler: string[];
  tesekkur_metni: string | null;
  yonlendirme_adresi: string | null;
  izinli_alanlar: string[];
  /** Faz 4G: gönder düğmesinin altındaki aydınlatma satırı (boşsa hazır metin). */
  aydinlatma_metni: string;
  aydinlatma_baglantisi: string | null;
  /** Aydınlatma metni/bağlantısı sürümü (eski adıyla KVKK sürümü). */
  kvkk_surum: number;
  /** Faz 4G: isteğe bağlı pazarlama izni kutusu gösterilsin mi. */
  pazarlama_izni_sor: boolean;
  aktif: boolean;
  gonderim_sayisi: number;
  son_gonderim_at: string | null;
  created_at: string | null;
}

export interface FormListesi {
  formlar: CrmFormu[];
  site_adresi: string;
  her_zaman_izinli: string[];
  alan_adlari: FormAlani[];
  alan_sinirlari: Record<FormAlani, number>;
}

export interface DavetSonucu {
  ok: boolean;
  link: string;
  email_status: string;
  email_detail: string;
  subject: string;
  message: string;
}

export class CrmHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {},
  ) {
    super(kod);
  }
}

/** Hata → seçili dilde metin (bilinmeyen kod → genel). */
export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof CrmHatasi) {
    const alan = typeof e.ek.alan === 'string' ? t(`crm.alan.${e.ek.alan}`, { defaultValue: e.ek.alan }) : '';
    return t(`crm.hata.${e.kod}`, { ...e.ek, alan, defaultValue: t('crm.hata.genel') }) as string;
  }
  return t('crm.hata.genel');
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

function hataCoz(durum: number, detay: unknown): CrmHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new CrmHatasi(durum, kod, ek);
  }
  return new CrmHatasi(durum, 'genel');
}

async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    throw hataCoz(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

const K = '/api/v1/crm';

function sorgu(p: Record<string, string | number | undefined | null>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v));
  const m = s.toString();
  return m ? `?${m}` : '';
}

export interface Suzgec {
  sorumlu?: string;
  kaynak?: string;
  etiket?: string;
  ara?: string;
}

export const metaGetir = () => istek<CrmMeta>('GET', `${K}/meta`);
export const kanbanGetir = (s: Suzgec) => istek<{ asamalar: KanbanSutunu[] }>('GET', `${K}/kanban${sorgu({ ...s })}`);
export const adayListesi = (s: Suzgec & { asama?: string; siralama?: string; sayfa?: number; boyut?: number }) =>
  istek<{ items: Aday[]; toplam: number; sayfa: number; boyut: number }>('GET', `${K}/adaylar${sorgu({ ...s })}`);
export const adayGetir = (id: number) =>
  istek<{ aday: AdayAyrintisi; aktiviteler: Aktivite[]; bagli_kayitlar: BagliKayit[] }>('GET', `${K}/adaylar/${id}`);
export const adayOlustur = (veri: Record<string, unknown>) => istek<AdayAyrintisi>('POST', `${K}/adaylar`, veri);
export const adayGuncelle = (id: number, veri: Record<string, unknown>) =>
  istek<AdayAyrintisi>('PATCH', `${K}/adaylar/${id}`, veri);
export const adaySil = (id: number) => istek<{ silindi: boolean }>('DELETE', `${K}/adaylar/${id}`);
export const asamaTasi = (id: number, asama: string, kaybedilme_nedeni?: string) =>
  istek<{ aday: AdayAyrintisi; degisti: boolean }>('POST', `${K}/adaylar/${id}/asama`, {
    asama,
    ...(kaybedilme_nedeni !== undefined ? { kaybedilme_nedeni } : {}),
  });
export const aktiviteEkle = (id: number, tur: ElleAktivite, metin: string) =>
  istek<{ aktivite: Aktivite; aday: AdayAyrintisi }>('POST', `${K}/adaylar/${id}/aktivite`, { tur, metin });
export const musteriyeDonustur = (id: number, proje_basligi?: string) =>
  istek<{ aday: AdayAyrintisi; davet: DavetSonucu }>('POST', `${K}/adaylar/${id}/donustur`, { proje_basligi });
export const asamaListesi = () => istek<{ asamalar: Asama[] }>('GET', `${K}/asamalar`);
export const asamaEkle = (veri: Record<string, unknown>) => istek<Asama>('POST', `${K}/asamalar`, veri);
export const asamaGuncelle = (anahtar: string, veri: Record<string, unknown>) =>
  istek<Asama>('PATCH', `${K}/asamalar/${encodeURIComponent(anahtar)}`, veri);
export const asamaSirala = (anahtarlar: string[]) => istek<{ asamalar: Asama[] }>('PUT', `${K}/asamalar/sira`, { anahtarlar });
export const asamaSil = (anahtar: string, hedef?: string) =>
  istek<{ silindi: boolean; tasinan: number }>('DELETE', `${K}/asamalar/${encodeURIComponent(anahtar)}${sorgu({ hedef })}`);
export const ozetGetir = () => istek<Ozet>('GET', `${K}/ozet`);
export const iceAktar = () =>
  istek<{ olusturulan: number; eklenen: number; atlanan: number; kalan: number }>('POST', `${K}/ice-aktar`);
export const formListesi = () => istek<FormListesi>('GET', `${K}/formlar`);
export const formOlustur = (veri: Record<string, unknown>) => istek<CrmFormu>('POST', `${K}/formlar`, veri);
export const formGuncelle = (id: number, veri: Record<string, unknown>) =>
  istek<CrmFormu>('PATCH', `${K}/formlar/${id}`, veri);
export const formSil = (id: number) => istek<{ silindi: boolean }>('DELETE', `${K}/formlar/${id}`);

/** Aşamanın seçili dildeki adı (çevirisi yoksa Türkçe). */
export function asamaAdi(a: Pick<Asama, 'ad' | 'ceviriler'> | undefined | null, dil: string): string {
  if (!a) return '—';
  const kisa = (dil || 'tr').slice(0, 2);
  return (kisa !== 'tr' && a.ceviriler?.[kisa]?.ad) || a.ad;
}

/** Aşama rengi → kenarlık/rozet sınıfları (Tailwind; tam sınıf adları burada sabit). */
export const RENK_SINIFI: Record<string, { kenar: string; rozet: string; nokta: string }> = {
  slate: { kenar: 'border-white/10', rozet: 'bg-white/10 text-foreground/80', nokta: 'bg-slate-400' },
  sky: { kenar: 'border-sky-400/30', rozet: 'bg-sky-500/15 text-sky-200', nokta: 'bg-sky-400' },
  violet: { kenar: 'border-violet-400/30', rozet: 'bg-violet-500/15 text-violet-200', nokta: 'bg-violet-400' },
  amber: { kenar: 'border-amber-400/30', rozet: 'bg-amber-500/15 text-amber-200', nokta: 'bg-amber-400' },
  orange: { kenar: 'border-orange-400/30', rozet: 'bg-orange-500/15 text-orange-200', nokta: 'bg-orange-400' },
  emerald: { kenar: 'border-emerald-400/30', rozet: 'bg-emerald-500/15 text-emerald-200', nokta: 'bg-emerald-400' },
  rose: { kenar: 'border-rose-400/30', rozet: 'bg-rose-500/15 text-rose-200', nokta: 'bg-rose-400' },
  pink: { kenar: 'border-pink-400/30', rozet: 'bg-pink-500/15 text-pink-200', nokta: 'bg-pink-400' },
  teal: { kenar: 'border-teal-400/30', rozet: 'bg-teal-500/15 text-teal-200', nokta: 'bg-teal-400' },
};

export const renk = (ad: string | undefined) => RENK_SINIFI[ad || 'slate'] || RENK_SINIFI.slate;

export function paraGoster(tutar: number | null | undefined, birim: string, dil: string): string {
  if (tutar === null || tutar === undefined) return '';
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: birim || 'TRY', maximumFractionDigits: 0 }).format(tutar);
  } catch {
    return `${Math.round(tutar)} ${birim}`;
  }
}

export function toplamlarGoster(toplam: Record<string, number>, dil: string): string {
  const parcalar = Object.entries(toplam || {})
    .filter(([, v]) => v)
    .map(([k, v]) => paraGoster(v, k, dil));
  return parcalar.join(' · ');
}

export function tarihGoster(deger: string | null | undefined, dil: string, saatli = false): string {
  if (!deger) return '';
  const d = deger.length === 10 ? new Date(`${deger}T00:00:00`) : new Date(deger);
  if (Number.isNaN(d.getTime())) return deger;
  try {
    return new Intl.DateTimeFormat(dil, saatli ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(d);
  } catch {
    return d.toISOString().slice(0, saatli ? 16 : 10);
  }
}

/** Gömme kodu (müşterinin sitesine yapıştırılır). */
export function gommeKodu(taban: string, anahtar: string): string {
  const t = taban.replace(/\/$/, '');
  return `<script src="${t}/crm-form.js" async></script>\n<div data-mk-form="${anahtar}"></div>`;
}
