import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { client } from '@/lib/sdkClient';

/**
 * Faz 3T — teklif, sözleşme ve fatura ekranlarının ortak yardımcıları.
 *
 * * Toplamlar SUNUCUDA hesaplanıyor (Decimal, kuruş); ön yüz yalnız kalemleri
 *   gönderiyor ve sunucunun döndürdüğü toplamı gösteriyor.
 * * Hata gövdesi `{detail: {kod}}`: metni ön yüz yedi dilde kendisi kuruyor.
 * * Para biçimi dile duyarlı (`Intl.NumberFormat`).
 */

export interface Kalem {
  aciklama: string;
  adet: number | string;
  birim_fiyat: number | string;
  kdv_orani: number | string;
  indirim: number | string;
  matrah?: number;
  kdv?: number;
  toplam?: number;
  indirim_tutari?: number;
}

export interface KdvSatiri {
  oran: number;
  matrah: number;
  kdv: number;
}

export interface BelgeOzeti {
  ara_toplam: number | null;
  indirim_toplam: number | null;
  kdv_toplam: number | null;
  genel_toplam: number | null;
  kdv_dokumu: KdvSatiri[];
}

export const PARA_BIRIMLERI = ['TRY', 'USD', 'EUR', 'GBP'] as const;
export const KDV_ORANLARI = [0, 1, 10, 20] as const;

export const bosKalem = (): Kalem => ({ aciklama: '', adet: 1, birim_fiyat: '', kdv_orani: 20, indirim: 0 });

export class BelgeHatasi extends Error {
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

function detayCoz(govde: unknown): { kod: string | null; ek: Record<string, unknown> } {
  const detay = (govde as { detail?: unknown } | null)?.detail;
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return { kod, ek };
  }
  return { kod: null, ek: {} };
}

function varsayilanKod(durum: number): string {
  if (durum === 401) return 'oturum_gerekli';
  if (durum === 403) return 'yetki_yok';
  if (durum === 404) return 'bulunamadi';
  if (durum === 409) return 'kullanildi';
  if (durum === 410) return 'suresi_doldu';
  if (durum === 429) return 'sinir';
  return 'genel';
}

export function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

/** Oturumlu istek (yönetici + müşteri; etkin hesap başlığı SDK'da ekleniyor). */
export async function istek<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> | undefined });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: unknown } };
    const durum = h?.response?.status ?? h?.status ?? 0;
    const { kod, ek } = detayCoz(h?.response?.data);
    throw new BelgeHatasi(durum, kod ?? varsayilanKod(durum), ek);
  }
}

function jeton(): string | null {
  try {
    return localStorage.getItem('token');
  } catch {
    return null;
  }
}

/** Çok parçalı form (dekont yükleme) — oturum + hesap başlığıyla. */
export async function formGonder<T>(url: string, form: FormData): Promise<T> {
  const basliklar: Record<string, string> = { ...hesapBasliklari() };
  const j = jeton();
  if (j) basliklar.Authorization = `Bearer ${j}`;
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, { method: 'POST', body: form, headers: basliklar });
  } catch {
    throw new BelgeHatasi(0, 'ag');
  }
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) {
    const { kod, ek } = detayCoz(govde);
    throw new BelgeHatasi(yanit.status, kod ?? varsayilanKod(yanit.status), ek);
  }
  return govde as T;
}

/** Girişsiz (jetonlu) istek: oturum başlığı GÖNDERİLMEZ — jetonun kendisi yetki. */
export async function acikIstek<T>(method: string, url: string, data?: unknown): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, {
      method,
      headers: data ? { 'Content-Type': 'application/json' } : undefined,
      body: data ? JSON.stringify(data) : undefined,
    });
  } catch {
    throw new BelgeHatasi(0, 'ag');
  }
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) {
    const { kod, ek } = detayCoz(govde);
    throw new BelgeHatasi(yanit.status, kod ?? varsayilanKod(yanit.status), ek);
  }
  return govde as T;
}

/**
 * PDF'i indirir. Oturumlu uçlarda jeton başlıkta gidiyor (bağlantı adresle
 * açılamaz); girişsiz uçta `oturumsuz=true` ve adresin kendisi yeterli.
 */
export async function pdfIndir(url: string, dosyaAdi: string, oturumsuz = false): Promise<void> {
  const basliklar: Record<string, string> = oturumsuz ? {} : { ...hesapBasliklari() };
  const j = oturumsuz ? null : jeton();
  if (j) basliklar.Authorization = `Bearer ${j}`;
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${url}`, { headers: basliklar });
  } catch {
    throw new BelgeHatasi(0, 'ag');
  }
  if (!yanit.ok) {
    const govde = await yanit.json().catch(() => null);
    const { kod, ek } = detayCoz(govde);
    throw new BelgeHatasi(yanit.status, kod ?? varsayilanKod(yanit.status), ek);
  }
  const blob = await yanit.blob();
  const adres = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = adres;
  a.download = dosyaAdi;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(adres), 30000);
}

/** PDF etiketlerinin dili: sitenin 7 dili (Faz 7K — sunucu bütün dillerde etiket ve yazı tipi taşıyor). */
export const PDF_DILLERI = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
export type PdfDili = (typeof PDF_DILLERI)[number];

export function pdfDili(dil: string): PdfDili {
  const d = (dil || 'tr').slice(0, 2).toLowerCase();
  return (PDF_DILLERI as readonly string[]).includes(d) ? (d as PdfDili) : 'en';
}

// ---------------------------------------------------------------------------
// Biçim
// ---------------------------------------------------------------------------
const YEREL: Record<string, string> = {
  tr: 'tr-TR',
  en: 'en-US',
  de: 'de-DE',
  ru: 'ru-RU',
  zh: 'zh-CN',
  hi: 'hi-IN',
  ar: 'ar',
};

export function yerel(dil: string): string {
  return YEREL[dil] || dil || 'tr-TR';
}

/** Dile duyarlı para: 1250.5, TRY, tr → "₺1.250,50"; en → "TRY 1,250.50" gibi. */
export function paraBicimle(deger: number | string | null | undefined, para: string | null | undefined, dil: string): string {
  if (deger == null || deger === '') return '—';
  const sayi = typeof deger === 'number' ? deger : Number(deger);
  if (!Number.isFinite(sayi)) return '—';
  try {
    return new Intl.NumberFormat(yerel(dil), {
      style: 'currency',
      currency: para || 'TRY',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(sayi);
  } catch {
    return `${sayi.toFixed(2)} ${para || 'TRY'}`;
  }
}

export function sayiBicimle(deger: number | string | null | undefined, dil: string): string {
  if (deger == null || deger === '') return '—';
  const sayi = typeof deger === 'number' ? deger : Number(deger);
  if (!Number.isFinite(sayi)) return String(deger);
  return new Intl.NumberFormat(yerel(dil), { maximumFractionDigits: 4 }).format(sayi);
}

/** "2026-10-01" ya da ISO an → yerel kısa tarih. */
export function tarihBicimle(deger: string | null | undefined, dil: string, saatli = false): string {
  if (!deger) return '—';
  const an = /^\d{4}-\d{2}-\d{2}$/.test(deger) ? new Date(`${deger}T12:00:00`) : new Date(deger);
  if (Number.isNaN(an.getTime())) return deger;
  try {
    return an.toLocaleString(yerel(dil), saatli
      ? { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }
      : { year: 'numeric', month: 'short', day: '2-digit' });
  } catch {
    return deger.slice(0, 10);
  }
}

export function bugunIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function gunEkle(iso: string, gun: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + gun);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Sunucuya giden kalem: yalnız girdi alanları (toplamlar gönderilmez). */
export function kalemGirdisi(k: Kalem): Record<string, unknown> {
  return {
    aciklama: (k.aciklama || '').trim(),
    adet: k.adet === '' ? 1 : k.adet,
    birim_fiyat: k.birim_fiyat === '' ? 0 : k.birim_fiyat,
    kdv_orani: k.kdv_orani === '' ? 0 : k.kdv_orani,
    indirim: k.indirim === '' ? 0 : k.indirim,
  };
}

/** Kalemlerden toplam önizlemesi (sunucu kuralıyla, yönetici ucu). */
export function kalemHesapla(url: string, kalemler: Kalem[], tur?: string) {
  return istek<{ kalemler: Kalem[] } & BelgeOzeti>('POST', url, { kalemler: kalemler.map(kalemGirdisi), tur });
}
