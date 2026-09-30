import { client } from '@/lib/sdkClient';

/**
 * Kredi defteri (Kullandıkça Öde): 1 kredi = 1 saat senior işçilik.
 *
 * Bakiye sunucuda, hareketlerin yeniden oynatılmasıyla (FIFO) hesaplanıyor;
 * ön yüz hiçbir zaman kendisi toplamıyor. Yönetici uçları
 * `/api/v1/kredi/yonetim`, müşteri ucu `/api/v1/kredilerim` (e-posta jetondan).
 */

export type KrediTuru = 'satin_alma' | 'bonus' | 'harcama' | 'iade' | 'hediye' | 'duzeltme' | 'sure_dolumu';
export type YuklemeTuru = 'hediye' | 'iade' | 'duzeltme' | 'satin_alma';

export const KREDI_TURLERI: KrediTuru[] = ['satin_alma', 'bonus', 'harcama', 'iade', 'hediye', 'duzeltme', 'sure_dolumu'];

export interface KrediHareketi {
  id: number;
  created_at?: string | null;
  miktar: number;
  tur: KrediTuru | string;
  aciklama?: string | null;
  fatura_id?: number | null;
  proje_id?: number | null;
  son_kullanma?: string | null;
  olusturan_eposta?: string | null;
}

export interface SonKullanma {
  miktar: number;
  tarih: string;
}

export interface KrediMusterisi {
  eposta: string;
  bakiye: number;
  borc: number;
  hareket_sayisi: number;
  son_hareket?: string | null;
  son_hareket_turu?: string | null;
  en_yakin_son_kullanma?: string | null;
  en_yakin_miktar?: number | null;
  dolum_bekleyen: number;
}

export interface KrediMusteriAyrintisi {
  eposta: string;
  bakiye: number;
  borc: number;
  yaklasan_son_kullanma: SonKullanma[];
  hareketler: KrediHareketi[];
}

export interface Kredilerim {
  bakiye: number;
  yaklasan_son_kullanma: SonKullanma[];
  hareketler: KrediHareketi[];
}

export interface KrediIslemSonucu {
  hareket: KrediHareketi;
  bakiye: number;
}

/** Uçtan dönen hata; `kod` sunucunun `detail` metni (ör. `yetersiz_bakiye`). */
export class KrediHatasi extends Error {
  durum: number;
  kod: string;

  constructor(durum: number, kod: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
  }
}

/** SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz. */
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
    throw new KrediHatasi(durum, typeof detay === 'string' ? detay : 'genel');
  }
}

const YONETIM = '/api/v1/kredi/yonetim';

export async function krediMusterileri(): Promise<KrediMusterisi[]> {
  const govde = await istek<KrediMusterisi[]>('GET', `${YONETIM}/musteriler`);
  return Array.isArray(govde) ? govde : [];
}

export async function krediMusterisi(eposta: string): Promise<KrediMusteriAyrintisi> {
  const govde = await istek<KrediMusteriAyrintisi>('GET', `${YONETIM}/musteri/${encodeURIComponent(eposta)}`);
  return {
    eposta: govde?.eposta ?? eposta,
    bakiye: govde?.bakiye ?? 0,
    borc: govde?.borc ?? 0,
    yaklasan_son_kullanma: govde?.yaklasan_son_kullanma ?? [],
    hareketler: govde?.hareketler ?? [],
  };
}

export function saatHarca(girdi: {
  eposta: string;
  saat: number;
  aciklama: string;
  proje_id?: number | null;
  izin_eksi?: boolean;
}): Promise<KrediIslemSonucu> {
  return istek<KrediIslemSonucu>('POST', `${YONETIM}/harca`, { ...girdi });
}

export function krediEkle(girdi: {
  eposta: string;
  saat: number;
  tur: YuklemeTuru;
  aciklama: string;
  fatura_id?: number | null;
}): Promise<KrediIslemSonucu> {
  return istek<KrediIslemSonucu>('POST', `${YONETIM}/yukle`, { ...girdi });
}

export function sureDolumlariniIsle(): Promise<{ musteri: number; yazilan: number; toplam_saat: number }> {
  return istek('POST', `${YONETIM}/sure-dolumlari`);
}

export async function kredilerimiGetir(): Promise<Kredilerim> {
  const govde = await istek<Kredilerim>('GET', '/api/v1/kredilerim');
  return {
    bakiye: govde?.bakiye ?? 0,
    yaklasan_son_kullanma: govde?.yaklasan_son_kullanma ?? [],
    hareketler: govde?.hareketler ?? [],
  };
}

/** Saat değerini seçili dilin sayı biçimiyle yazar (0.25 hassasiyet). */
export function saatBicimle(deger: number, dil: string): string {
  try {
    return new Intl.NumberFormat(dil, { maximumFractionDigits: 2 }).format(deger);
  } catch {
    return String(deger);
  }
}

export function tarihBicimle(deger: string | null | undefined, dil: string): string {
  if (!deger) return '—';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '—';
  try {
    return an.toLocaleDateString(dil, { year: 'numeric', month: 'short', day: '2-digit' });
  } catch {
    return an.toISOString().slice(0, 10);
  }
}

/** Bugünden kaç gün sonra (geçmişse eksi). */
export function kalanGun(deger: string | null | undefined): number | null {
  if (!deger) return null;
  const an = new Date(deger).getTime();
  if (Number.isNaN(an)) return null;
  return Math.ceil((an - Date.now()) / 86_400_000);
}

/** Son kullanmaya kalan güne göre renk: ≤30 gün kırmızı, ≤90 sarı. */
export function sonKullanmaRengi(gun: number | null): string {
  if (gun === null) return 'text-muted-foreground';
  if (gun <= 30) return 'text-red-300';
  if (gun <= 90) return 'text-amber-300';
  return 'text-emerald-300';
}

/** Tür rozetinin renk sınıfları. */
export function turRengi(tur: string): string {
  switch (tur) {
    case 'satin_alma':
      return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300';
    case 'bonus':
    case 'hediye':
      return 'border-purple-400/30 bg-purple-500/10 text-purple-300';
    case 'iade':
      return 'border-sky-400/30 bg-sky-500/10 text-sky-300';
    case 'harcama':
      return 'border-amber-400/30 bg-amber-500/10 text-amber-300';
    case 'sure_dolumu':
      return 'border-red-400/30 bg-red-500/10 text-red-300';
    default:
      return 'border-white/10 bg-white/5 text-muted-foreground';
  }
}
