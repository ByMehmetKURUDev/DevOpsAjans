import { client } from '@/lib/sdkClient';
import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 2A — müşteri sitesi bakımı: bitiş tarihleri, uptime, durum sayfası,
 * yenileme yöneticisi ve zamanlanmış görevler.
 *
 * Yönetici  /api/v1/site-bakim, /api/v1/yenilemeler, /api/v1/zamanli/yonetim
 * Müşteri   /api/v1/sitelerim-bakim
 * Açık      /api/v1/durum/<slug>  (girişsiz; düz fetch)
 */

export type GuncelDurum = 'calisiyor' | 'kesinti' | 'bilinmiyor';
export type YenilemeTuru = 'alan' | 'ssl' | 'hosting' | 'abonelik';

export interface Izleme {
  alan_adi: string | null;
  alan_bitis: string | null;
  alan_kalan: number | null;
  alan_bitis_kaynak: 'rdap' | 'elle' | null;
  alan_rdap_hata: string | null;
  alan_saglayici: string | null;
  ssl_bitis: string | null;
  ssl_kalan: number | null;
  ssl_hata: string | null;
  ssl_elle_yenilenir: boolean;
  hosting_bitis: string | null;
  hosting_kalan: number | null;
  hosting_saglayici: string | null;
  notlar?: string | null;
  alan_kontrol_at: string | null;
  durum_sayfasi_acik: boolean;
  durum_slug: string | null;
  durum_index: boolean;
}

export interface GunCubugu {
  gun: string;
  oran: number | null;
  olcum?: number;
}

export interface Kesinti {
  id?: number;
  baslangic: string | null;
  bitis: string | null;
  sure_dk: number | null;
  sebep?: string | null;
}

export interface UptimeOzeti {
  guncel: GuncelDurum;
  kontrol_sayisi?: number;
  son_kontrol: string | null;
  oran_24s: number | null;
  oran_7g: number | null;
  oran_30g: number | null;
  oran_90g: number | null;
  gunler: GunCubugu[];
  kesintiler: Kesinti[];
}

export interface UptimeKontrolu {
  id: number;
  site_id: number;
  url: string;
  aralik_dk: number;
  anahtar_kelime: string | null;
  beklenen_kod: number;
  acik: boolean;
  son_kontrol_at: string | null;
  son_durum: 'up' | 'down' | null;
  ardisik_hata: number;
}

export interface BakimKarti {
  site_id: number;
  ad: string;
  adres: string | null;
  client_email: string;
  izleme: Izleme;
  durum_adresi: string | null;
  uptime_modulu: boolean;
  yenileme_modulu: boolean;
  uptime: UptimeOzeti | null;
  kontroller?: UptimeKontrolu[];
}

export interface DurumSayfasiYaniti {
  durum_sayfasi_acik: boolean;
  durum_index: boolean;
  durum_slug: string | null;
  durum_adresi: string | null;
}

export interface AcikDurum extends Partial<UptimeOzeti> {
  ad: string;
  index: boolean;
}

export interface YenilemeFaturasi {
  invoice_id: number;
  invoice_no: string;
  status: string | null;
  tutar: number;
  para_birimi: string | null;
  odeme_adresi: string | null;
  adres?: string | null;
  mevcut?: boolean;
}

export interface YenilemeKalemi {
  tur: YenilemeTuru;
  ref_id: number;
  site_id: number | null;
  abonelik_id: number | null;
  client_email: string;
  baslik: string;
  bitis: string;
  kalan_gun: number;
  saglayici: string | null;
  tutar: number | null;
  para_birimi: string | null;
  periyot: string | null;
  modul_acik: boolean;
  fatura: YenilemeFaturasi | null;
}

export interface ZamanliSatir {
  gorev?: string;
  siklik_dk?: number;
  son_calisma: string | null;
  sure_ms: number | null;
  sonuc: Record<string, unknown> | null;
  hata: string | null;
  calisma_sayisi: number;
}

export interface ZamanliDurum {
  genel: ZamanliSatir & { calisiyor: boolean };
  /** `plan` (Faz 7O): sıklıktan farklı takvim, ör. "haftalik_pazartesi". */
  gorevler: (ZamanliSatir & { gorev: string; siklik_dk: number; plan?: string | null })[];
  anahtar_tanimli: boolean;
  atlandi?: boolean;
  sebep?: string | null;
}

/** Uçtan dönen hata; `kod` sunucunun `detail.kod`u (ör. `adres_yasak`). */
export class BakimHatasi extends Error {
  durum: number;
  kod: string;

  constructor(durum: number, kod: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
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
    const kod =
      typeof detay === 'string'
        ? detay
        : detay && typeof detay === 'object' && 'kod' in (detay as Record<string, unknown>)
          ? String((detay as { kod: unknown }).kod)
          : 'genel';
    throw new BakimHatasi(durum, kod);
  }
}

// --- Yönetici ---------------------------------------------------------------
const BAKIM = '/api/v1/site-bakim';

export async function bakimKartlari(): Promise<BakimKarti[]> {
  const govde = await istek<BakimKarti[]>('GET', BAKIM);
  return Array.isArray(govde) ? govde : [];
}

export function bakimKarti(siteId: number): Promise<BakimKarti> {
  return istek<BakimKarti>('GET', `${BAKIM}/${siteId}`);
}

export function izlemeGuncelle(
  siteId: number,
  girdi: Partial<{
    alan_adi: string;
    alan_bitis: string;
    alan_saglayici: string;
    hosting_bitis: string;
    hosting_saglayici: string;
    ssl_elle_yenilenir: boolean;
    notlar: string;
  }>,
): Promise<BakimKarti> {
  return istek<BakimKarti>('PUT', `${BAKIM}/${siteId}`, girdi as Record<string, unknown>);
}

export function simdiTara(siteId: number): Promise<BakimKarti> {
  return istek<BakimKarti>('POST', `${BAKIM}/${siteId}/tara`);
}

export function kontrolEkle(
  siteId: number,
  girdi: { url: string; aralik_dk?: number; anahtar_kelime?: string; beklenen_kod?: number },
): Promise<UptimeKontrolu> {
  return istek<UptimeKontrolu>('POST', `${BAKIM}/${siteId}/uptime`, girdi);
}

export function kontrolGuncelle(
  kontrolId: number,
  girdi: Partial<{ url: string; aralik_dk: number; anahtar_kelime: string; beklenen_kod: number; acik: boolean }>,
): Promise<UptimeKontrolu> {
  return istek<UptimeKontrolu>('PATCH', `${BAKIM}/uptime/${kontrolId}`, girdi as Record<string, unknown>);
}

export function kontrolSil(kontrolId: number): Promise<{ silindi: number }> {
  return istek('DELETE', `${BAKIM}/uptime/${kontrolId}`);
}

export function yoneticiDurumSayfasi(siteId: number, acik: boolean, index?: boolean): Promise<DurumSayfasiYaniti> {
  return istek('POST', `${BAKIM}/${siteId}/durum-sayfasi`, index === undefined ? { acik } : { acik, index });
}

// --- Yenilemeler -------------------------------------------------------------
export async function yenilemeleriGetir(gun = 90): Promise<{ gun: number; bugun: string; kalemler: YenilemeKalemi[] }> {
  const govde = await istek<{ gun: number; bugun: string; kalemler: YenilemeKalemi[] }>(
    'GET',
    `/api/v1/yenilemeler?gun=${gun}`,
  );
  return { gun: govde?.gun ?? gun, bugun: govde?.bugun ?? '', kalemler: govde?.kalemler ?? [] };
}

export function yenilemeFaturasiKes(girdi: {
  tur: YenilemeTuru;
  ref_id: number;
  tutar: number;
  para_birimi?: string;
  aciklama?: string;
  son_odeme?: string;
  eposta_gonder?: boolean;
}): Promise<YenilemeFaturasi> {
  return istek('POST', '/api/v1/yenilemeler/fatura', girdi);
}

// --- Zamanlı görevler --------------------------------------------------------
export function zamanliDurum(): Promise<ZamanliDurum> {
  return istek('GET', '/api/v1/zamanli/yonetim');
}

export function zamanliCalistir(): Promise<ZamanliDurum> {
  return istek('POST', '/api/v1/zamanli/yonetim/calistir');
}

// --- Müşteri -----------------------------------------------------------------
export async function kendiBakimKartlarim(): Promise<BakimKarti[]> {
  const govde = await istek<BakimKarti[]>('GET', '/api/v1/sitelerim-bakim');
  return Array.isArray(govde) ? govde : [];
}

export function musteriDurumSayfasi(siteId: number, acik: boolean, index?: boolean): Promise<DurumSayfasiYaniti> {
  return istek(
    'POST',
    `/api/v1/sitelerim-bakim/${siteId}/durum-sayfasi`,
    index === undefined ? { acik } : { acik, index },
  );
}

// --- Herkese açık --------------------------------------------------------------
export async function acikDurumGetir(slug: string): Promise<AcikDurum> {
  const yanit = await fetch(`${getAPIBaseURL()}/api/v1/durum/${encodeURIComponent(slug)}`, {
    headers: { accept: 'application/json' },
  });
  if (!yanit.ok) throw new BakimHatasi(yanit.status, yanit.status === 404 ? 'sayfa_yok' : 'genel');
  return (await yanit.json()) as AcikDurum;
}

// --- Biçim yardımcıları -----------------------------------------------------------
/** Bitişe kalan güne göre rozet rengi: >30 yeşil, ≤30 sarı, ≤7 kırmızı. */
export function bitisRengi(gun: number | null | undefined): string {
  if (gun === null || gun === undefined) return 'border-white/10 bg-white/[0.04] text-muted-foreground';
  if (gun <= 7) return 'border-red-400/40 bg-red-500/15 text-red-200';
  if (gun <= 30) return 'border-amber-400/40 bg-amber-500/15 text-amber-200';
  return 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200';
}

/** Gün çubuğunun rengi (erişilebilirlik %). */
export function oranRengi(oran: number | null | undefined): string {
  if (oran === null || oran === undefined) return 'bg-white/10';
  if (oran >= 99.5) return 'bg-emerald-400';
  if (oran >= 97) return 'bg-lime-400';
  if (oran >= 90) return 'bg-amber-400';
  return 'bg-red-500';
}

export function yuzdeBicimle(oran: number | null | undefined, dil: string): string {
  if (oran === null || oran === undefined) return '—';
  try {
    return `${new Intl.NumberFormat(dil, { maximumFractionDigits: 2 }).format(oran)}%`;
  } catch {
    return `${oran}%`;
  }
}

export function tarihBicimle(deger: string | null | undefined, dil: string, saatli = false): string {
  if (!deger) return '—';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '—';
  try {
    return saatli
      ? an.toLocaleString(dil, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      : an.toLocaleDateString(dil, { year: 'numeric', month: 'short', day: '2-digit' });
  } catch {
    return an.toISOString().slice(0, saatli ? 16 : 10);
  }
}

/** `<input type="date">` değeri (YYYY-MM-DD) — ISO tarihten. */
export function tarihGirdisi(deger: string | null | undefined): string {
  return deger ? deger.slice(0, 10) : '';
}
