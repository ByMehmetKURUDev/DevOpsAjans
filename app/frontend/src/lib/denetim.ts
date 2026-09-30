import { client } from '@/lib/sdkClient';

/**
 * Denetim kaydı (kim, ne zaman, hangi kaydı, neyi değiştirdi).
 *
 * Kayıtlar arka uçta SQLAlchemy flush olayından kendiliğinden yazılıyor;
 * burada yalnız okuma uçları var. Yönetici bütün kaydı alan bazında farkla
 * görüyor; müşteri yalnız `/benim` — kendi yaptıkları ve kendi kayıtlarına
 * yapılanlar, farksız.
 */

export type DenetimIslemi = 'olustur' | 'guncelle' | 'sil' | 'giris' | 'onay' | 'odeme' | 'diger';
export type AktorRolu = 'admin' | 'client' | 'sistem' | 'anonim';

export interface DenetimSatiri {
  id: number;
  created_at?: string | null;
  aktor_eposta?: string | null;
  aktor_rol?: AktorRolu | string | null;
  islem: DenetimIslemi | string;
  tablo: string;
  kayit_id?: string | null;
  ozet?: string | null;
  /** {"alan": [eski, yeni]} — hassas alanlar "***". */
  degisiklik?: Record<string, [unknown, unknown]> | null;
  istek_yolu?: string | null;
  ip_ozeti?: string | null;
}

export interface DenetimListesi {
  items: DenetimSatiri[];
  total: number;
  skip: number;
  limit: number;
}

export interface SayiSatiri {
  ad: string;
  sayi: number;
}

export interface DenetimOzeti {
  gun: number;
  toplam: number;
  tablolar: SayiSatiri[];
  aktorler: SayiSatiri[];
  islemler: SayiSatiri[];
}

export interface FiltreSecenekleri {
  tablolar: string[];
  islemler: string[];
  roller: string[];
}

export interface DenetimFiltresi {
  aktor?: string;
  tablo?: string;
  islem?: string;
  kayit_id?: string;
  /** YYYY-AA-GG (dahil) */
  baslangic?: string;
  /** YYYY-AA-GG (dahil) */
  bitis?: string;
}

export interface HareketSatiri {
  id: number;
  created_at?: string | null;
  islem: DenetimIslemi | string;
  tablo: string;
  kayit_id?: string | null;
  ozet?: string | null;
  kendisi: boolean;
  aktor_rol?: AktorRolu | string | null;
}

/** SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz. */
function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

async function al<T>(url: string): Promise<T | undefined> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url });
  return govdeyiAc<T>(yanit);
}

export async function denetimListesi(
  filtre: DenetimFiltresi,
  skip = 0,
  limit = 50
): Promise<DenetimListesi> {
  const sorgu = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  for (const [ad, deger] of Object.entries(filtre)) {
    const temiz = (deger ?? '').toString().trim();
    if (temiz) sorgu.set(ad, temiz);
  }
  const govde = await al<Partial<DenetimListesi>>(`/api/v1/denetim?${sorgu}`);
  return {
    items: Array.isArray(govde?.items) ? govde!.items : [],
    total: govde?.total ?? 0,
    skip: govde?.skip ?? skip,
    limit: govde?.limit ?? limit,
  };
}

export async function denetimOzeti(): Promise<DenetimOzeti> {
  const govde = await al<Partial<DenetimOzeti>>('/api/v1/denetim/ozet');
  return {
    gun: govde?.gun ?? 7,
    toplam: govde?.toplam ?? 0,
    tablolar: govde?.tablolar ?? [],
    aktorler: govde?.aktorler ?? [],
    islemler: govde?.islemler ?? [],
  };
}

export async function filtreSecenekleri(): Promise<FiltreSecenekleri> {
  const govde = await al<Partial<FiltreSecenekleri>>('/api/v1/denetim/tablolar');
  return {
    tablolar: govde?.tablolar ?? [],
    islemler: govde?.islemler ?? [],
    roller: govde?.roller ?? [],
  };
}

export async function hesapHareketlerim(): Promise<HareketSatiri[]> {
  const govde = await al<HareketSatiri[]>('/api/v1/denetim/benim');
  return Array.isArray(govde) ? govde : [];
}

/** İşlem rozetinin renk sınıfları. */
export function islemRengi(islem: string): string {
  switch (islem) {
    case 'olustur':
      return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300';
    case 'guncelle':
      return 'border-sky-400/30 bg-sky-500/10 text-sky-300';
    case 'sil':
      return 'border-red-400/30 bg-red-500/10 text-red-300';
    case 'odeme':
      return 'border-amber-400/30 bg-amber-500/10 text-amber-300';
    case 'onay':
      return 'border-purple-400/30 bg-purple-500/10 text-purple-300';
    case 'giris':
      return 'border-white/15 bg-white/5 text-foreground/80';
    default:
      return 'border-white/10 bg-white/5 text-muted-foreground';
  }
}

/** "3 dakika önce" — tarayıcının kendi dil verisiyle (çeviri gerekmiyor). */
export function goreliZaman(deger: string | null | undefined, dil: string): string {
  if (!deger) return '—';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '—';
  const saniye = Math.round((an.getTime() - Date.now()) / 1000);
  const birimler: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31_536_000],
    ['month', 2_592_000],
    ['week', 604_800],
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ];
  let bicim: Intl.RelativeTimeFormat;
  try {
    bicim = new Intl.RelativeTimeFormat(dil, { numeric: 'auto' });
  } catch {
    bicim = new Intl.RelativeTimeFormat('tr', { numeric: 'auto' });
  }
  for (const [birim, boy] of birimler) {
    if (Math.abs(saniye) >= boy) return bicim.format(Math.round(saniye / boy), birim);
  }
  return bicim.format(saniye, 'second');
}

export function tamZaman(deger: string | null | undefined, dil: string): string {
  if (!deger) return '';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '';
  return an.toLocaleString(dil, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}
