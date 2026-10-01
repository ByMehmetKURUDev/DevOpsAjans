import { client } from '@/lib/sdkClient';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 2C — dosyalar, paylaşım bağlantısı ve belge talebi.
 *
 * Yönetici  /api/v1/dosyalar, /api/v1/belge-talepleri
 * Müşteri   /api/v1/dosyalarim  (modül `dosyalar`)
 * Açık      /api/v1/paylas/<jeton>, /api/v1/dosya-indir/<id>?son&imza
 *
 * Yükleme `multipart/form-data`: SDK'nın `apiCall.invoke`'u JSON gönderiyor,
 * o yüzden yüklemeler düz `fetch` + oturum jetonu ile.
 */

export type Gorunurluk = 'musteri' | 'ekip';

export interface Dosya {
  id: number;
  client_email: string;
  proje_id: number | null;
  klasor: string;
  ad: string;
  boyut: number;
  tur: string;
  uzanti: string;
  yukleyen_rol: 'admin' | 'client' | null;
  surum: number;
  belge_talebi_id: number | null;
  created_at: string | null;
  gorunurluk: Gorunurluk | null;
}

export interface Klasor {
  ad: string;
  gorunurluk: Gorunurluk;
}

export interface Paylasim {
  id: number;
  dosya_id: number;
  son_kullanma: string;
  sifreli: boolean;
  indirme_siniri: number | null;
  indirme_sayisi: number;
  durum: 'gecerli' | 'suresi_doldu' | 'iptal' | 'sinir_doldu' | 'kilitli';
  yol?: string;
  adres?: string;
}

export interface BelgeTalebi {
  id: number;
  client_email: string;
  baslik: string;
  aciklama: string | null;
  son_tarih: string | null;
  kalan_gun: number | null;
  kabul_turleri: string[];
  durum: 'bekliyor' | 'teslim_edildi' | 'iptal';
  dosya: Dosya | null;
  teslim_at: string | null;
  created_at: string | null;
}

export interface DepoBilgisi {
  tur: 's3' | 'veritabani';
  kalici: boolean;
  oneri: string | null;
  boyut_siniri_mb: number;
  izinli_turler: string[];
}

export interface MusteriDosyalari {
  klasorler: string[];
  dosyalar: Dosya[];
  boyut_siniri_mb: number;
  izinli_turler: string[];
}

export interface PaylasimBilgisi {
  ad: string;
  boyut: number;
  tur: string;
  sifreli: boolean;
  son_kullanma: string;
  kalan_indirme: number | null;
}

/** Ön yüzün yedi dilde metin kurduğu hata (`dosyalar.hata.<kod>`). */
export class DosyaHatasi extends Error {
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

function hataCoz(durum: number, detay: unknown): DosyaHatasi {
  if (detay && typeof detay === 'object') {
    const d = detay as Record<string, unknown>;
    const { kod, ...ek } = d;
    return new DosyaHatasi(durum, typeof kod === 'string' ? kod : 'genel', ek);
  }
  return new DosyaHatasi(durum, durum === 413 ? 'boyut_asildi' : 'genel');
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
  // Faz 2E: ekip üyesi başka hesapta çalışıyorsa o hesabın başlığı da gider.
  const basliklar: Record<string, string> = { ...hesapBasliklari() };
  const j = jeton();
  if (j) basliklar.Authorization = `Bearer ${j}`;
  const yanit = await fetch(`${getAPIBaseURL()}${url}`, { method: 'POST', body: form, headers: basliklar });
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) throw hataCoz(yanit.status, (govde as { detail?: unknown } | null)?.detail);
  return govde as T;
}

async function acikIstek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  const yanit = await fetch(`${getAPIBaseURL()}${url}`, {
    method,
    headers: data ? { 'Content-Type': 'application/json' } : undefined,
    body: data ? JSON.stringify(data) : undefined,
  });
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) throw hataCoz(yanit.status, (govde as { detail?: unknown } | null)?.detail);
  return govde as T;
}

/** İmzalı (süreli) adresi tarayıcıda indirir. */
export function adresiIndir(yol: string): void {
  const a = document.createElement('a');
  a.href = `${getAPIBaseURL()}${yol}`;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function boyutBicimle(bayt: number, dil: string): string {
  const b = Number(bayt) || 0;
  const fmt = (n: number) => n.toLocaleString(dil, { maximumFractionDigits: 1 });
  if (b >= 1024 * 1024) return `${fmt(b / (1024 * 1024))} MB`;
  if (b >= 1024) return `${fmt(b / 1024)} KB`;
  return `${b} B`;
}

export function tarihBicimle(deger: string | null | undefined, dil: string, saatli = false): string {
  if (!deger) return '—';
  const t = new Date(deger.length === 10 ? `${deger}T12:00:00` : deger);
  if (Number.isNaN(t.getTime())) return '—';
  return t.toLocaleString(dil, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(saatli ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}

// --------------------------------------------------------------------------
// Yönetici
// --------------------------------------------------------------------------
export const depoBilgisi = () => istek<DepoBilgisi>('GET', '/api/v1/dosyalar/depo');

export const boyutSiniriKaydet = (mb: number) =>
  istek<{ boyut_siniri_mb: number }>('PUT', '/api/v1/dosyalar/ayarlar', { boyut_siniri_mb: mb });

export async function yoneticiDosyalari(eposta: string): Promise<{ dosyalar: Dosya[]; klasorler: Klasor[] }> {
  const g = await istek<{ dosyalar: Dosya[]; klasorler: Klasor[] }>(
    'GET',
    `/api/v1/dosyalar?client_email=${encodeURIComponent(eposta)}`
  );
  return { dosyalar: g?.dosyalar ?? [], klasorler: g?.klasorler ?? [] };
}

export const klasorKaydet = (eposta: string, ad: string, gorunurluk: Gorunurluk) =>
  istek<Klasor>('POST', '/api/v1/dosyalar/klasorler', { client_email: eposta, ad, gorunurluk });

export function yoneticiYukle(
  eposta: string,
  dosya: File,
  klasor: string,
  gorunurluk: Gorunurluk
): Promise<Dosya> {
  const f = new FormData();
  f.append('client_email', eposta);
  f.append('klasor', klasor);
  f.append('gorunurluk', gorunurluk);
  f.append('dosya', dosya, dosya.name);
  return formGonder<Dosya>('/api/v1/dosyalar/yukle', f);
}

export const dosyaSil = (id: number) => istek<{ silindi: number }>('DELETE', `/api/v1/dosyalar/${id}`);

export const yoneticiIndirmeAdresi = (id: number) =>
  istek<{ adres: string; son: number }>('POST', `/api/v1/dosyalar/${id}/indirme-baglantisi`, {});

export const paylasimOlustur = (id: number, girdi: { gun: number; sifre?: string; indirme_siniri?: number | null }) =>
  istek<Paylasim>('POST', `/api/v1/dosyalar/${id}/paylasim`, girdi as Record<string, unknown>);

export async function paylasimlar(id: number): Promise<Paylasim[]> {
  const g = await istek<Paylasim[]>('GET', `/api/v1/dosyalar/${id}/paylasimlar`);
  return Array.isArray(g) ? g : [];
}

export const paylasimIptal = (id: number) => istek<Paylasim>('POST', `/api/v1/dosyalar/paylasim/${id}/iptal`, {});

export async function belgeTalepleri(eposta?: string): Promise<BelgeTalebi[]> {
  const g = await istek<BelgeTalebi[]>(
    'GET',
    `/api/v1/belge-talepleri${eposta ? `?client_email=${encodeURIComponent(eposta)}` : ''}`
  );
  return Array.isArray(g) ? g : [];
}

export const belgeTalebiAc = (girdi: {
  client_email: string;
  baslik: string;
  aciklama?: string;
  son_tarih?: string;
  kabul_turleri?: string[];
}) => istek<BelgeTalebi>('POST', '/api/v1/belge-talepleri', girdi as Record<string, unknown>);

export const belgeTalebiIptal = (id: number) => istek<BelgeTalebi>('POST', `/api/v1/belge-talepleri/${id}/iptal`, {});

// --------------------------------------------------------------------------
// Müşteri
// --------------------------------------------------------------------------
export async function dosyalarim(): Promise<MusteriDosyalari> {
  const g = await istek<MusteriDosyalari>('GET', '/api/v1/dosyalarim');
  return {
    klasorler: g?.klasorler ?? [],
    dosyalar: g?.dosyalar ?? [],
    boyut_siniri_mb: g?.boyut_siniri_mb ?? 20,
    izinli_turler: g?.izinli_turler ?? [],
  };
}

export function musteriYukle(dosya: File, klasor?: string): Promise<Dosya> {
  const f = new FormData();
  if (klasor) f.append('klasor', klasor);
  f.append('dosya', dosya, dosya.name);
  return formGonder<Dosya>('/api/v1/dosyalarim/yukle', f);
}

export const musteriIndirmeAdresi = (id: number) =>
  istek<{ adres: string; son: number }>('POST', `/api/v1/dosyalarim/${id}/indirme-baglantisi`, {});

export async function istenenBelgeler(): Promise<BelgeTalebi[]> {
  const g = await istek<BelgeTalebi[]>('GET', '/api/v1/dosyalarim/talepler');
  return Array.isArray(g) ? g : [];
}

export function talebeYukle(talepId: number, dosya: File): Promise<BelgeTalebi> {
  const f = new FormData();
  f.append('dosya', dosya, dosya.name);
  return formGonder<BelgeTalebi>(`/api/v1/dosyalarim/talepler/${talepId}/yukle`, f);
}

// --------------------------------------------------------------------------
// Açık (girişsiz) paylaşım
// --------------------------------------------------------------------------
export const paylasimBilgisi = (jetonDegeri: string) =>
  acikIstek<PaylasimBilgisi>('GET', `/api/v1/paylas/${encodeURIComponent(jetonDegeri)}`);

export const paylasimdanIndir = (jetonDegeri: string, sifre?: string) =>
  acikIstek<{ adres: string; son: number; ad: string }>(
    'POST',
    `/api/v1/paylas/${encodeURIComponent(jetonDegeri)}/indir`,
    { sifre: sifre || null }
  );
