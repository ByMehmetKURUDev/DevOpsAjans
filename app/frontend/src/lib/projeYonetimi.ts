import { client } from '@/lib/sdkClient';
import { hesapBasliklari } from '@/lib/hesapSecimi';
import { getAPIBaseURL } from '@/lib/config';

/**
 * Faz 2B — proje yönetimi: görevler (Kanban), revizyon sayacı, hata/geri
 * bildirim, duyurular ve öneri kutusu.
 *
 * Yönetici  /api/v1/gorevler, /api/v1/geri-bildirim, /api/v1/duyurular, /api/v1/oneri-yonetimi
 * Müşteri   /api/v1/gorevlerim, /api/v1/geri-bildirimlerim, /api/v1/duyurularim, /api/v1/oneri-kutusu
 * Açık      /api/v1/topluluk-onerileri (girişsiz; düz fetch)
 */

export const GOREV_DURUMLARI = ['yapilacak', 'suruyor', 'incelemede', 'tamam'] as const;
export type GorevDurumu = (typeof GOREV_DURUMLARI)[number];
export const ONCELIKLER = ['dusuk', 'normal', 'yuksek', 'acil'] as const;
export type Oncelik = (typeof ONCELIKLER)[number];

export interface KontrolMaddesi {
  id: number;
  gorev_id: number;
  metin: string;
  tamam: boolean;
  sira: number;
}

export interface Gorev {
  id: number;
  proje_id: number;
  baslik: string;
  aciklama: string | null;
  durum: GorevDurumu;
  oncelik: Oncelik;
  atanan: string | null;
  bitis_tarihi: string | null;
  sira: number;
  musteriye_gorunur: boolean;
  ust_gorev_id: number | null;
  kilometre_tasi: boolean;
  tahmini_saat: number | null;
  harcanan_saat: number;
  etiketler: string[];
  geri_bildirim_id: number | null;
  tamamlandi_at: string | null;
  created_at: string | null;
  kontrol_listesi: KontrolMaddesi[];
  bagimliliklar: number[];
  bekleyen_bagimliliklar: number[];
}

export interface RevizyonSayaci {
  ay: string;
  kullanilan: number;
  krediden: number;
  hak: number | null;
  kalan: number | null;
  asim: number;
  asildi: boolean;
  kaynak: 'paket' | 'proje' | null;
  paket?: string | null;
  istek_sayisi: number;
}

export interface GeriBildirimEki {
  id: number;
  icerik_turu: string;
  boyut: number;
  dosya_adi: string | null;
  adres: string;
}

export type GeriBildirimTuru = 'hata' | 'oneri' | 'soru';
export type GeriBildirimDurumu = 'yeni' | 'inceleniyor' | 'gorev' | 'cozuldu' | 'kapatildi';
export const GERI_BILDIRIM_TURLERI: GeriBildirimTuru[] = ['hata', 'oneri', 'soru'];
export const GERI_BILDIRIM_DURUMLARI: GeriBildirimDurumu[] = ['yeni', 'inceleniyor', 'gorev', 'cozuldu', 'kapatildi'];

export interface GeriBildirim {
  id: number;
  proje_id: number | null;
  proje_basligi: string | null;
  tur: GeriBildirimTuru;
  baslik: string;
  aciklama: string | null;
  sayfa_adresi: string | null;
  durum: GeriBildirimDurumu;
  ekler: GeriBildirimEki[];
  created_at: string | null;
  updated_at: string | null;
  // Yalnız yönetici
  musteri_eposta?: string;
  tarayici?: string | null;
  oncelik?: Oncelik;
  gorev_id?: number | null;
}

export interface EkipUyesi {
  ad: string;
  email: string;
}

export interface ProjeGorevleriYaniti {
  proje: { id: number; baslik: string; client_email: string | null; aylik_revizyon_saati: number | null };
  gorevler: Gorev[];
  geri_bildirimler: GeriBildirim[];
  revizyon: RevizyonSayaci | null;
  kredi_modulu: boolean;
  ekip: EkipUyesi[];
}

export interface MusteriGorevi {
  id: number;
  baslik: string;
  aciklama: string | null;
  durum: GorevDurumu;
  oncelik: Oncelik;
  bitis_tarihi: string | null;
  sira: number;
  ust_gorev_id: number | null;
  kilometre_tasi: boolean;
  kontrol: { tamam: number; toplam: number };
  tamamlandi_at: string | null;
}

export interface MusteriGorunumu {
  proje: { id: number; baslik: string };
  gorevler: MusteriGorevi[];
  ilerleme: { toplam: number; tamam: number; yuzde: number };
  kilometre_taslari: MusteriGorevi[];
}

export interface SaatGirisi {
  id: number;
  gorev_id: number;
  saat: number;
  tarih: string;
  aciklama: string | null;
  revizyon: boolean;
  kredi_saat: number | null;
  giren_eposta: string | null;
  created_at: string | null;
}

export interface SaatYaniti {
  giris: SaatGirisi | null;
  gorev: Gorev;
  revizyon: RevizyonSayaci | null;
  kredi_bakiye: number | null;
}

export type DuyuruOnemi = 'bilgi' | 'onemli' | 'kritik';
export type DuyuruHedefi = 'tum' | 'secili' | 'ekip';
export const DUYURU_ONEMLERI: DuyuruOnemi[] = ['bilgi', 'onemli', 'kritik'];
export const DUYURU_HEDEFLERI: DuyuruHedefi[] = ['tum', 'secili', 'ekip'];

export interface Duyuru {
  id: number;
  baslik: string;
  metin: string | null;
  onem: DuyuruOnemi;
  bitis_at: string | null;
  created_at: string | null;
  okundu: boolean;
  kapatildi: boolean;
}

export interface YoneticiDuyurusu {
  id: number;
  baslik: string;
  metin: string | null;
  onem: DuyuruOnemi;
  hedef: DuyuruHedefi;
  hedef_epostalar: string[];
  bitis_at: string | null;
  yayinda: boolean;
  etkin: boolean;
  okunma_sayisi: number;
  kapatma_sayisi: number;
  created_at: string | null;
}

export type OneriDurumu = 'yeni' | 'inceleniyor' | 'planlandi' | 'yapildi' | 'reddedildi';
export const ONERI_DURUMLARI: OneriDurumu[] = ['yeni', 'inceleniyor', 'planlandi', 'yapildi', 'reddedildi'];

export interface Oneri {
  id: number;
  baslik: string;
  aciklama: string | null;
  durum: OneriDurumu;
  yonetici_notu: string | null;
  oy_sayisi: number;
  benim: boolean;
  oyladim: boolean;
  created_at: string | null;
}

export interface YoneticiOnerisi {
  id: number;
  baslik: string;
  aciklama: string | null;
  durum: OneriDurumu;
  yonetici_notu: string | null;
  oy_sayisi: number;
  sahip_eposta: string;
  created_at: string | null;
}

/** Uçtan dönen hata; `kod` sunucunun `detail.kod`u, `ek` diğer alanlar (ör. `gorevler`). */
export class ProjeHatasi extends Error {
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

function hatayaCevir(durum: number, detay: unknown): ProjeHatasi {
  if (detay && typeof detay === 'object') {
    const { kod, ...ek } = detay as Record<string, unknown>;
    return new ProjeHatasi(durum, typeof kod === 'string' ? kod : 'genel', ek);
  }
  return new ProjeHatasi(durum, 'genel');
}

async function istek<T>(method: string, url: string, data?: Record<string, unknown>): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    throw hatayaCevir(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

function jeton(): string | null {
  try {
    return localStorage.getItem('token');
  } catch {
    return null;
  }
}

/** Oturumlu düz fetch (çok parçalı yükleme ve görsel indirme için). */
async function oturumluFetch(yol: string, init: RequestInit = {}): Promise<Response> {
  const j = jeton();
  const basliklar = new Headers(init.headers || {});
  if (j) basliklar.set('Authorization', `Bearer ${j}`);
  // Faz 2E: etkin müşteri hesabı (ekip üyesi başka hesapta çalışıyorsa).
  for (const [ad, deger] of Object.entries(hesapBasliklari())) basliklar.set(ad, deger);
  return fetch(`${getAPIBaseURL()}${yol}`, { ...init, headers: basliklar });
}

// --- Görevler (yönetici) -------------------------------------------------------
const G = '/api/v1/gorevler';

export function projeGorevleri(projeId: number): Promise<ProjeGorevleriYaniti> {
  return istek('GET', `${G}/proje/${projeId}`);
}

export type GorevGirdisi = Partial<{
  baslik: string;
  aciklama: string | null;
  durum: GorevDurumu;
  oncelik: Oncelik;
  atanan: string | null;
  bitis_tarihi: string | null;
  musteriye_gorunur: boolean;
  ust_gorev_id: number | null;
  kilometre_tasi: boolean;
  tahmini_saat: number | null;
  etiketler: string[];
}>;

export function gorevEkle(projeId: number, girdi: GorevGirdisi): Promise<Gorev> {
  return istek('POST', `${G}/proje/${projeId}`, girdi as Record<string, unknown>);
}

export function gorevGuncelle(gorevId: number, girdi: GorevGirdisi): Promise<Gorev> {
  return istek('PATCH', `${G}/${gorevId}`, girdi as Record<string, unknown>);
}

export function gorevSil(gorevId: number): Promise<{ silindi: number }> {
  return istek('DELETE', `${G}/${gorevId}`);
}

export function siraKaydet(
  projeId: number,
  gorevler: { id: number; durum: GorevDurumu; sira: number }[],
): Promise<{ gorevler: Gorev[] }> {
  return istek('PUT', `${G}/proje/${projeId}/sira`, { gorevler });
}

export function revizyonHakkiAyarla(
  projeId: number,
  saat: number | null,
): Promise<{ aylik_revizyon_saati: number | null; revizyon: RevizyonSayaci | null }> {
  return istek('PUT', `${G}/proje/${projeId}/revizyon`, { aylik_revizyon_saati: saat });
}

export function kontrolEkle(gorevId: number, metin: string): Promise<Gorev> {
  return istek('POST', `${G}/${gorevId}/kontrol`, { metin });
}

export function kontrolGuncelle(kontrolId: number, girdi: Partial<{ metin: string; tamam: boolean }>): Promise<Gorev> {
  return istek('PATCH', `${G}/kontrol/${kontrolId}`, girdi);
}

export function kontrolSil(kontrolId: number): Promise<Gorev> {
  return istek('DELETE', `${G}/kontrol/${kontrolId}`);
}

export function bagimlilikEkle(gorevId: number, bagliId: number): Promise<Gorev> {
  return istek('POST', `${G}/${gorevId}/bagimlilik`, { bagli_oldugu_id: bagliId });
}

export function bagimlilikSil(gorevId: number, bagliId: number): Promise<Gorev> {
  return istek('DELETE', `${G}/${gorevId}/bagimlilik/${bagliId}`);
}

export async function saatleriGetir(gorevId: number): Promise<SaatGirisi[]> {
  const govde = await istek<{ girisler: SaatGirisi[] }>('GET', `${G}/${gorevId}/saat`);
  return govde?.girisler ?? [];
}

export function saatGir(
  gorevId: number,
  girdi: { saat: number; tarih?: string; aciklama?: string; krediden_dus?: boolean; kredi_saat?: number },
): Promise<SaatYaniti> {
  return istek('POST', `${G}/${gorevId}/saat`, girdi);
}

export function saatiKredidenDus(girisId: number, saat?: number): Promise<SaatYaniti> {
  return istek('POST', `${G}/saat/${girisId}/kredi`, saat === undefined ? {} : { saat });
}

export function saatSil(girisId: number): Promise<{ silindi: number }> {
  return istek('DELETE', `${G}/saat/${girisId}`);
}

// --- Görevler (müşteri) ----------------------------------------------------------
export function musteriGorevleri(projeId: number): Promise<MusteriGorunumu> {
  return istek('GET', `/api/v1/gorevlerim/proje/${projeId}`);
}

export function revizyonSayacim(): Promise<RevizyonSayaci> {
  return istek('GET', '/api/v1/gorevlerim/revizyon');
}

// --- Geri bildirim -----------------------------------------------------------------
export const EN_BUYUK_EKRAN = 5 * 1024 * 1024;
export const IZINLI_GORSELLER = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

export async function geriBildirimGonder(girdi: {
  baslik: string;
  aciklama?: string;
  tur: GeriBildirimTuru;
  sayfa_adresi?: string;
  tarayici?: string;
  proje_id?: number | null;
  ekran?: File | null;
}): Promise<GeriBildirim> {
  const form = new FormData();
  form.set('baslik', girdi.baslik);
  form.set('tur', girdi.tur);
  if (girdi.aciklama) form.set('aciklama', girdi.aciklama);
  if (girdi.sayfa_adresi) form.set('sayfa_adresi', girdi.sayfa_adresi);
  if (girdi.tarayici) form.set('tarayici', girdi.tarayici);
  if (girdi.proje_id) form.set('proje_id', String(girdi.proje_id));
  if (girdi.ekran) form.set('ekran', girdi.ekran, girdi.ekran.name || 'ekran.png');
  const yanit = await oturumluFetch('/api/v1/geri-bildirimlerim', { method: 'POST', body: form });
  const govde = await yanit.json().catch(() => null);
  if (!yanit.ok) throw hatayaCevir(yanit.status, govde?.detail);
  return govde as GeriBildirim;
}

export async function geriBildirimlerim(): Promise<GeriBildirim[]> {
  const govde = await istek<GeriBildirim[]>('GET', '/api/v1/geri-bildirimlerim');
  return Array.isArray(govde) ? govde : [];
}

/** Ek görseli oturumla indirip nesne adresine çevirir (img src için). */
export async function ekAdresi(adres: string): Promise<string> {
  const yanit = await oturumluFetch(adres);
  if (!yanit.ok) throw new ProjeHatasi(yanit.status, 'ek_okunamadi');
  return URL.createObjectURL(await yanit.blob());
}

export async function geriBildirimListesi(suzgec: { durum?: string; proje_id?: number; tur?: string } = {}): Promise<GeriBildirim[]> {
  const p = new URLSearchParams();
  if (suzgec.durum) p.set('durum', suzgec.durum);
  if (suzgec.proje_id) p.set('proje_id', String(suzgec.proje_id));
  if (suzgec.tur) p.set('tur', suzgec.tur);
  const q = p.toString();
  const govde = await istek<GeriBildirim[]>('GET', `/api/v1/geri-bildirim${q ? `?${q}` : ''}`);
  return Array.isArray(govde) ? govde : [];
}

export function geriBildirimGuncelle(id: number, girdi: Partial<{ durum: GeriBildirimDurumu; oncelik: Oncelik }>): Promise<GeriBildirim> {
  return istek('PATCH', `/api/v1/geri-bildirim/${id}`, girdi);
}

export function goreveDonustur(id: number, musteriye_gorunur = true): Promise<{ geri_bildirim: GeriBildirim; gorev: Gorev }> {
  return istek('POST', `/api/v1/geri-bildirim/${id}/goreve-donustur`, { musteriye_gorunur });
}

// --- Duyurular -------------------------------------------------------------------
export async function duyurularim(): Promise<{ duyurular: Duyuru[]; okunmamis: number }> {
  const govde = await istek<{ duyurular: Duyuru[]; okunmamis: number }>('GET', '/api/v1/duyurularim');
  return { duyurular: govde?.duyurular ?? [], okunmamis: govde?.okunmamis ?? 0 };
}

export function duyuruOkundu(id: number): Promise<Duyuru> {
  return istek('POST', `/api/v1/duyurularim/${id}/okundu`);
}

export function duyuruKapat(id: number): Promise<Duyuru> {
  return istek('POST', `/api/v1/duyurularim/${id}/kapat`);
}

export async function duyuruListesi(): Promise<YoneticiDuyurusu[]> {
  const govde = await istek<YoneticiDuyurusu[]>('GET', '/api/v1/duyurular');
  return Array.isArray(govde) ? govde : [];
}

export type DuyuruGirdisi = {
  baslik: string;
  metin?: string;
  onem: DuyuruOnemi;
  hedef: DuyuruHedefi;
  hedef_epostalar?: string[];
  bitis?: string;
  yayinda?: boolean;
  bildirim_gonder?: boolean;
};

export function duyuruEkle(girdi: DuyuruGirdisi): Promise<YoneticiDuyurusu> {
  return istek('POST', '/api/v1/duyurular', girdi as unknown as Record<string, unknown>);
}

export function duyuruGuncelle(id: number, girdi: Partial<DuyuruGirdisi>): Promise<YoneticiDuyurusu> {
  return istek('PATCH', `/api/v1/duyurular/${id}`, girdi as Record<string, unknown>);
}

export function duyuruSil(id: number): Promise<{ silindi: number }> {
  return istek('DELETE', `/api/v1/duyurular/${id}`);
}

// --- Öneri kutusu ----------------------------------------------------------------
export async function oneriler(): Promise<Oneri[]> {
  const govde = await istek<Oneri[]>('GET', '/api/v1/oneri-kutusu');
  return Array.isArray(govde) ? govde : [];
}

export function oneriGonder(baslik: string, aciklama?: string): Promise<Oneri> {
  return istek('POST', '/api/v1/oneri-kutusu', { baslik, aciklama });
}

export function oyVer(id: number): Promise<Oneri> {
  return istek('POST', `/api/v1/oneri-kutusu/${id}/oy`);
}

export function oyGeriAl(id: number): Promise<Oneri> {
  return istek('DELETE', `/api/v1/oneri-kutusu/${id}/oy`);
}

export async function oneriYonetimi(): Promise<{ oneriler: YoneticiOnerisi[]; topluluk_yol_haritasi: boolean }> {
  const govde = await istek<{ oneriler: YoneticiOnerisi[]; topluluk_yol_haritasi: boolean }>('GET', '/api/v1/oneri-yonetimi');
  return { oneriler: govde?.oneriler ?? [], topluluk_yol_haritasi: !!govde?.topluluk_yol_haritasi };
}

export function oneriGuncelle(id: number, girdi: Partial<{ durum: OneriDurumu; yonetici_notu: string }>): Promise<YoneticiOnerisi> {
  return istek('PATCH', `/api/v1/oneri-yonetimi/${id}`, girdi);
}

export function toplulukAyari(acik: boolean): Promise<{ topluluk_yol_haritasi: boolean }> {
  return istek('PUT', '/api/v1/oneri-yonetimi/ayar', { topluluk_yol_haritasi: acik });
}

/** Yol haritası › Topluluktan (girişsiz). Hata/kapalı → boş liste. */
export async function toplulukOnerileri(): Promise<{ baslik: string; oy_sayisi: number }[]> {
  try {
    const y = await fetch(`${getAPIBaseURL()}/api/v1/topluluk-onerileri`);
    if (!y.ok) return [];
    const g = (await y.json()) as { acik?: boolean; oneriler?: { baslik: string; oy_sayisi: number }[] };
    return g?.acik && Array.isArray(g.oneriler) ? g.oneriler : [];
  } catch {
    return [];
  }
}

// --- Biçim ----------------------------------------------------------------------
export function tarihGoster(deger: string | null | undefined, dil: string): string {
  if (!deger) return '';
  const d = deger.length <= 10 ? new Date(`${deger}T12:00:00Z`) : new Date(deger);
  if (Number.isNaN(d.getTime())) return deger;
  try {
    return d.toLocaleDateString(dil, { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return deger.slice(0, 10);
  }
}

export function saatGoster(s: number | null | undefined, dil: string): string {
  const n = typeof s === 'number' ? s : 0;
  try {
    return n.toLocaleString(dil, { maximumFractionDigits: 2 });
  } catch {
    return String(n);
  }
}
