import { client } from '@/lib/sdkClient';

/**
 * Faz 2D — oturum güvenliği uçları.
 *
 * Her giriş bir "oturum" satırı açıyor (cihaz, IP özeti, son görülme).
 * Kişi kendi oturumlarını görür/kapatır; yönetici herkesinkini görür, tek
 * oturumu kapatır ya da bir kullanıcıyı her yerden çıkarır. Oturum kimliği
 * (sid) hiçbir yanıtta dönmüyor.
 */

export interface Oturum {
  id: number;
  cihaz?: string | null;
  ip_ozet?: string | null;
  olusturma?: string | null;
  son_gorulme?: string | null;
  bitis?: string | null;
  bu_cihaz: boolean;
}

export interface YoneticiOturumu extends Oturum {
  email: string;
  rol?: string | null;
  etkin: boolean;
  iptal_zamani?: string | null;
  iptal_eden?: string | null;
}

export interface OturumListesi {
  items: YoneticiOturumu[];
  toplam: number;
  sayfa: number;
  adet: number;
}

export class GuvenlikHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string
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

async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    const detay = h?.response?.data?.detail as { kod?: unknown } | undefined;
    throw new GuvenlikHatasi(
      h?.response?.status ?? h?.status ?? 0,
      detay && typeof detay === 'object' && typeof detay.kod === 'string' ? detay.kod : 'genel'
    );
  }
}

// --- Kişi -------------------------------------------------------------------
export async function oturumlarim(): Promise<Oturum[]> {
  const g = await istek<Oturum[]>('GET', '/api/v1/oturumlarim');
  return Array.isArray(g) ? g : [];
}

export async function oturumumuKapat(id: number): Promise<{ kapatilan: number; bu_cihaz: boolean }> {
  return istek('DELETE', `/api/v1/oturumlarim/${id}`);
}

export async function digerleriniKapat(): Promise<{ kapatilan: number }> {
  return istek('POST', '/api/v1/oturumlarim/digerlerini-kapat');
}

// --- Yönetici -----------------------------------------------------------------
export async function oturumListesi(
  filtre: { email?: string; yalniz_etkin?: boolean },
  sayfa = 1,
  adet = 50
): Promise<OturumListesi> {
  const sorgu = new URLSearchParams({ sayfa: String(sayfa), adet: String(adet) });
  if (filtre.email?.trim()) sorgu.set('email', filtre.email.trim());
  sorgu.set('yalniz_etkin', filtre.yalniz_etkin === false ? 'false' : 'true');
  const g = await istek<Partial<OturumListesi>>('GET', `/api/v1/oturumlar?${sorgu}`);
  return {
    items: Array.isArray(g?.items) ? g!.items : [],
    toplam: g?.toplam ?? 0,
    sayfa: g?.sayfa ?? sayfa,
    adet: g?.adet ?? adet,
  };
}

export async function oturumuKapat(id: number): Promise<{ kapatilan: number }> {
  return istek('DELETE', `/api/v1/oturumlar/${id}`);
}

export async function kullaniciyiCikar(email: string): Promise<{ kapatilan: number }> {
  return istek('POST', '/api/v1/oturumlar/kullanici-cikis', { email });
}

// --- Faz 4G: CSP ihlal raporları (yalnız yönetici) ------------------------------
export interface CspRaporu {
  id: number;
  belge: string;
  yonerge: string;
  engellenen: string;
  kaynak_dosya: string | null;
  satir: number | null;
  sutun: number | null;
  mod: 'enforce' | 'report' | string;
  ornek: string | null;
  sayi: number;
  ilk_at: string | null;
  son_at: string | null;
}

export async function cspRaporlari(adet = 100): Promise<{ items: CspRaporu[]; toplam: number; sinir: number }> {
  const g = await istek<{ items: CspRaporu[]; toplam: number; sinir: number }>('GET', `/api/v1/csp-rapor/yonetim?adet=${adet}`);
  return { items: Array.isArray(g?.items) ? g.items : [], toplam: g?.toplam ?? 0, sinir: g?.sinir ?? 500 };
}

export async function cspRaporlariniTemizle(): Promise<{ silinen: number }> {
  return istek('DELETE', '/api/v1/csp-rapor/yonetim');
}
