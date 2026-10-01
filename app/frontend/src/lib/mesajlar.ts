import { client } from '@/lib/sdkClient';
import { getAPIBaseURL } from '@/lib/config';
import { hesapBasliklari } from '@/lib/hesapSecimi';

/**
 * Faz 2G — müşteri ↔ ajans mesajlaşma uçları.
 *
 * Müşteri `/api/v1/mesajlarim/...` (etkin hesap `X-MK-Hesap` başlığıyla —
 * istek katmanı ekliyor), yönetici `/api/v1/mesajlar/...`. Metin DÜZ METİN:
 * sunucu HTML'i olduğu gibi saklıyor, arayüz hiçbir zaman HTML olarak çizmiyor.
 *
 * Bu dosya müşteri/yönetici panelinin ana parçasına giriyor (sekme rozeti için
 * yalnız `ozetGetir`); sohbet arayüzü ayrı (lazy) parçada.
 */

export type Taraf = 'client' | 'admin';
export type KonusmaDurumu = 'acik' | 'arsiv';

export interface Konusma {
  id: number;
  hesap_email: string;
  hesap_adi?: string | null;
  konu: string;
  genel: boolean;
  proje_id?: number | null;
  durum: KonusmaDurumu;
  son_mesaj_at?: string | null;
  son_mesaj_id?: number | null;
  son_mesaj_ozet?: string | null;
  son_mesaj_rol?: Taraf | null;
  okunmamis: number;
  created_at?: string | null;
}

export interface KonusmaDetayi extends Konusma {
  projeler: { id: number; baslik: string }[];
}

export interface Ek {
  id: number;
  ad: string;
  boyut: number;
  tur?: string | null;
}

export interface Mesaj {
  id: number;
  konusma_id: number;
  yazan_rol: Taraf;
  yazan_ad?: string | null;
  yazan_email?: string | null;
  benim: boolean;
  metin: string;
  ekler: Ek[];
  silindi: boolean;
  duzenlendi_at?: string | null;
  created_at?: string | null;
  duzenleme_bitis?: string | null;
}

export interface MesajSayfasi {
  konusma: { id: number; durum: KonusmaDurumu; degisiklik: number; son_mesaj_id?: number | null };
  mesajlar: Mesaj[];
  daha_eski: boolean | null;
  karsi_okunan: number;
  okudugum: number;
}

export interface MesajOzeti {
  okunmamis: number;
  okunmamis_konusma: number;
  son_mesaj_id: number;
  konusma_sayisi: number;
  degisiklik: number;
}

export class MesajHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

function hataCoz(durum: number, detay: unknown): MesajHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new MesajHatasi(durum, kod, ek);
  }
  if (durum === 413) return new MesajHatasi(durum, 'boyut_asildi');
  if (durum === 429) return new MesajHatasi(durum, 'cok_hizli');
  return new MesajHatasi(durum, 'genel');
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

function jeton(): string | null {
  try {
    return localStorage.getItem('token');
  } catch {
    return null;
  }
}

async function formGonder<T>(url: string, form: FormData): Promise<T> {
  const basliklar: Record<string, string> = { ...hesapBasliklari() };
  const j = jeton();
  if (j) basliklar.Authorization = `Bearer ${j}`;
  const yanit = await fetch(`${getAPIBaseURL()}${url}`, { method: 'POST', body: form, headers: basliklar });
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) throw hataCoz(yanit.status, (govde as { detail?: unknown } | null)?.detail);
  return govde as T;
}

const taban = (taraf: Taraf) => (taraf === 'admin' ? '/api/v1/mesajlar' : '/api/v1/mesajlarim');

function sorgu(p: Record<string, string | number | boolean | null | undefined>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) {
    if (v === undefined || v === null || v === '' || v === false) continue;
    s.set(k, String(v));
  }
  const metin = s.toString();
  return metin ? `?${metin}` : '';
}

// --- Ortak ------------------------------------------------------------------
export const ozetGetir = (taraf: Taraf) => istek<MesajOzeti>('GET', `${taban(taraf)}/ozet`);

export async function konusmalariGetir(
  taraf: Taraf,
  suzgec: { durum?: string; q?: string; okunmamis?: boolean } = {}
): Promise<Konusma[]> {
  const g = await istek<{ konusmalar: Konusma[] }>(
    'GET',
    `${taban(taraf)}/konusmalar${taraf === 'admin' ? sorgu(suzgec) : ''}`
  );
  return Array.isArray(g?.konusmalar) ? g.konusmalar : [];
}

export const konusmaAc = (taraf: Taraf, girdi: { konu: string; proje_id?: number | null; hesap_email?: string }) =>
  istek<Konusma>('POST', `${taban(taraf)}/konusmalar`, girdi as unknown as Record<string, unknown>);

export const mesajlariGetir = (
  taraf: Taraf,
  konusmaId: number,
  p: { sonra?: number; once?: number; adet?: number } = {}
) => istek<MesajSayfasi>('GET', `${taban(taraf)}/konusmalar/${konusmaId}/mesajlar${sorgu(p)}`);

export const mesajGonder = (taraf: Taraf, konusmaId: number, girdi: { metin: string; ekler?: number[] }) =>
  istek<Mesaj>('POST', `${taban(taraf)}/konusmalar/${konusmaId}/mesajlar`, girdi as unknown as Record<string, unknown>);

export const okunduIsaretle = (taraf: Taraf, konusmaId: number, mesajId: number) =>
  istek<{ okudugum: number }>('POST', `${taban(taraf)}/konusmalar/${konusmaId}/okundu`, { mesaj_id: mesajId });

export const mesajDuzenle = (taraf: Taraf, mesajId: number, metin: string) =>
  istek<Mesaj>('PUT', `${taban(taraf)}/mesajlar/${mesajId}`, { metin });

export const mesajSil = (taraf: Taraf, mesajId: number) => istek<Mesaj>('DELETE', `${taban(taraf)}/mesajlar/${mesajId}`);

export function ekYukle(taraf: Taraf, konusmaId: number, dosya: File): Promise<Ek> {
  const f = new FormData();
  f.append('dosya', dosya, dosya.name);
  return formGonder<Ek>(taraf === 'admin' ? `/api/v1/mesajlar/konusmalar/${konusmaId}/ekler` : '/api/v1/mesajlarim/ekler', f);
}

export const ekIndirmeAdresi = (taraf: Taraf, mesajId: number, dosyaId: number) =>
  istek<{ adres: string; son: number }>('POST', `${taban(taraf)}/mesajlar/${mesajId}/ekler/${dosyaId}/indirme-baglantisi`, {});

// --- Yalnız yönetici --------------------------------------------------------
export const konusmaDetayi = (konusmaId: number) => istek<KonusmaDetayi>('GET', `/api/v1/mesajlar/konusmalar/${konusmaId}`);

export const konusmaGuncelle = (konusmaId: number, girdi: { durum?: KonusmaDurumu; konu?: string }) =>
  istek<Konusma>('PUT', `/api/v1/mesajlar/konusmalar/${konusmaId}`, girdi as unknown as Record<string, unknown>);

export const konusmaSil = (konusmaId: number) =>
  istek<{ silindi: number }>('DELETE', `/api/v1/mesajlar/konusmalar/${konusmaId}`);

export const hazirCevabiDoldur = (konusmaId: number, hazirCevapId: number) =>
  istek<{ metin: string }>('POST', `/api/v1/mesajlar/konusmalar/${konusmaId}/hazir-cevap`, { hazir_cevap_id: hazirCevapId });

export const talebeCevir = (konusmaId: number, mesajId?: number) =>
  istek<{ talep_id: number; konu: string }>('POST', `/api/v1/mesajlar/konusmalar/${konusmaId}/talep`, {
    mesaj_id: mesajId ?? null,
  });

export const goreveCevir = (konusmaId: number, projeId: number, mesajId?: number) =>
  istek<{ id: number; baslik: string }>('POST', `/api/v1/mesajlar/konusmalar/${konusmaId}/gorev`, {
    proje_id: projeId,
    mesaj_id: mesajId ?? null,
  });

/** İmzalı (süreli) adresi tarayıcıda indirir. */
export function adresiIndir(yol: string): void {
  const a = document.createElement('a');
  a.href = `${getAPIBaseURL()}${yol}`;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
}
