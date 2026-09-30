import { getAPIBaseURL } from '@/lib/config';
import { client } from '@/lib/sdkClient';

/**
 * İmzalı işlem bağlantıları (girişsiz tek tıkla onay) — tipler ve uç çağrıları.
 *
 * * Girişsiz sayfa `/islem/<jeton>`: düz `fetch` (oturum yok; jeton yetki).
 * * Yönetici `/api/v1/islem-yonetim`: bağlantı üret/listele/iptal/yenile.
 *   Ham bağlantı yalnız üretim yanıtında bir kez gelir.
 * * Müşteri `/api/v1/islemlerim`: kendi bekleyenleri; karar oturumla verilir.
 *
 * Hata gövdesi `{detail: {kod}}`; metni ön yüz yedi dilde kendisi kuruyor.
 */

export type IslemTuru = 'teklif_kabul' | 'teslimat_onay' | 'rapor_goruntule';
export type IslemDurumu = 'bekliyor' | 'kullanildi' | 'iptal' | 'suresi_doldu';
export type IslemSonucu = 'kabul' | 'red' | 'onay' | 'revizyon' | 'goruntulendi';

export const ISLEM_TURLERI: IslemTuru[] = ['teklif_kabul', 'teslimat_onay'];
export const ISLEM_DURUMLARI: IslemDurumu[] = ['bekliyor', 'kullanildi', 'iptal', 'suresi_doldu'];

/** Sunucunun kurduğu, sayfada gösterilen özet. Türe göre alanlar değişir. */
export interface IslemAyrintisi {
  // teklif
  teklif_id?: number;
  tutar?: number;
  para_birimi?: string;
  paket?: string | null;
  profil?: string | null;
  donem?: string | null;
  eklentiler?: string[];
  ai_pm?: string | null;
  kredi?: string | null;
  fatura_no?: string | null;
  // teslimat
  proje_id?: number;
  proje?: string;
  asama?: string | null;
  asama_etiketi?: string;
  baglanti?: string | null;
  ilerlet?: boolean;
  // rapor
  alan_adi?: string;
  puan?: number | null;
  // ortak
  not?: string | null;
}

/** Karar verilebilir bir işlem: girişsiz sayfa da müşteri paneli de bunu çizer. */
export interface KararlikIslem {
  tur: IslemTuru | string;
  baslik: string;
  ayrinti: IslemAyrintisi;
  durum: IslemDurumu | string;
  sonuclar: IslemSonucu[];
  not_zorunlu: IslemSonucu[];
  son_kullanma?: string | null;
}

export interface AcikIslem extends KararlikIslem {
  sonuc?: IslemSonucu | null;
  kullanildi_at?: string | null;
  alici: string;
}

export interface MusteriIslemi extends KararlikIslem {
  id: number;
  created_at?: string | null;
}

export interface KararYaniti {
  durum: IslemDurumu | string;
  sonuc?: IslemSonucu | null;
  kullanildi_at?: string | null;
}

export interface YonetimIslemi {
  id: number;
  tur: IslemTuru | string;
  hedef_tablo: string;
  hedef_id: number;
  alici_eposta: string;
  baslik: string;
  ayrinti: IslemAyrintisi;
  durum: IslemDurumu | string;
  sonuc?: IslemSonucu | null;
  sonuc_notu?: string | null;
  son_kullanma?: string | null;
  kullanildi_at?: string | null;
  olusturan_eposta?: string | null;
  created_at?: string | null;
}

export interface OlusturYaniti {
  islem: YonetimIslemi;
  baglanti: string;
  eposta_gonderildi: boolean;
  eski_id?: number | null;
}

export interface IslemHedefi {
  id: number;
  etiket: string;
  alici?: string | null;
  ek?: string | null;
}

export class IslemHatasi extends Error {
  durum: number;
  kod: string;

  constructor(durum: number, kod: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
  }
}

function kodCikar(govde: unknown): string | null {
  const detay = (govde as { detail?: unknown } | null)?.detail;
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    return (detay as { kod: string }).kod;
  }
  return null;
}

function varsayilanKod(durum: number): string {
  if (durum === 429) return 'sinir';
  if (durum === 404) return 'bulunamadi';
  if (durum === 409) return 'kullanildi';
  if (durum === 410) return 'suresi_doldu';
  return 'genel';
}

// ---------------------------------------------------------------------------
// Girişsiz
// ---------------------------------------------------------------------------
async function acikIstek<T>(jeton: string, govde?: Record<string, unknown>): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}/api/v1/islem/${encodeURIComponent(jeton)}`, {
      method: govde ? 'POST' : 'GET',
      headers: govde ? { 'Content-Type': 'application/json' } : undefined,
      body: govde ? JSON.stringify(govde) : undefined,
    });
  } catch {
    throw new IslemHatasi(0, 'ag');
  }
  let veri: unknown = null;
  try {
    veri = await yanit.json();
  } catch {
    veri = null;
  }
  if (!yanit.ok) throw new IslemHatasi(yanit.status, kodCikar(veri) ?? varsayilanKod(yanit.status));
  return veri as T;
}

export function islemGetir(jeton: string): Promise<AcikIslem> {
  return acikIstek<AcikIslem>(jeton);
}

export function islemKarari(jeton: string, sonuc: IslemSonucu, not?: string): Promise<KararYaniti> {
  return acikIstek<KararYaniti>(jeton, { sonuc, not: not || undefined });
}

// ---------------------------------------------------------------------------
// Oturumlu (yönetici + müşteri)
// ---------------------------------------------------------------------------
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
    const h = hata as { status?: number; response?: { status?: number; data?: unknown } };
    const durum = h?.response?.status ?? h?.status ?? 0;
    throw new IslemHatasi(durum, kodCikar(h?.response?.data) ?? varsayilanKod(durum));
  }
}

const YONETIM = '/api/v1/islem-yonetim';

export async function islemListesi(filtre: { tur?: string; durum?: string; hedef_tablo?: string; hedef_id?: number } = {}): Promise<YonetimIslemi[]> {
  const sorgu = new URLSearchParams();
  if (filtre.tur) sorgu.set('tur', filtre.tur);
  if (filtre.durum) sorgu.set('durum', filtre.durum);
  if (filtre.hedef_tablo) sorgu.set('hedef_tablo', filtre.hedef_tablo);
  if (filtre.hedef_id != null) sorgu.set('hedef_id', String(filtre.hedef_id));
  const q = sorgu.toString();
  const govde = await istek<YonetimIslemi[]>('GET', q ? `${YONETIM}?${q}` : YONETIM);
  return Array.isArray(govde) ? govde : [];
}

export async function islemHedefleri(tur: IslemTuru): Promise<IslemHedefi[]> {
  const govde = await istek<IslemHedefi[]>('GET', `${YONETIM}/hedefler?tur=${encodeURIComponent(tur)}`);
  return Array.isArray(govde) ? govde : [];
}

export function islemOlustur(girdi: {
  tur: IslemTuru;
  hedef_id: number;
  alici_eposta?: string;
  gun?: number;
  not?: string;
  baglanti?: string;
  ilerlet?: boolean;
  eposta_gonder?: boolean;
}): Promise<OlusturYaniti> {
  return istek<OlusturYaniti>('POST', `${YONETIM}/olustur`, { ...girdi });
}

export function islemIptal(id: number): Promise<YonetimIslemi> {
  return istek<YonetimIslemi>('POST', `${YONETIM}/${id}/iptal`);
}

export function islemYenile(id: number, girdi: { gun?: number; eposta_gonder?: boolean } = {}): Promise<OlusturYaniti> {
  return istek<OlusturYaniti>('POST', `${YONETIM}/${id}/yenile`, { ...girdi });
}

export async function islemlerim(): Promise<MusteriIslemi[]> {
  const govde = await istek<MusteriIslemi[]>('GET', '/api/v1/islemlerim');
  return Array.isArray(govde) ? govde : [];
}

export function islemlerimKarar(id: number, sonuc: IslemSonucu, not?: string): Promise<KararYaniti> {
  return istek<KararYaniti>('POST', `/api/v1/islemlerim/${id}`, { sonuc, not: not || undefined });
}

// ---------------------------------------------------------------------------
// Biçim
// ---------------------------------------------------------------------------
export function tutarBicimle(deger: number | undefined, para: string | undefined, dil: string): string {
  if (deger == null) return '—';
  try {
    return new Intl.NumberFormat(dil, { style: 'currency', currency: para || 'USD', maximumFractionDigits: 2 }).format(deger);
  } catch {
    return `${deger} ${para || 'USD'}`;
  }
}

export function tarihSaatBicimle(deger: string | null | undefined, dil: string): string {
  if (!deger) return '—';
  const an = new Date(deger);
  if (Number.isNaN(an.getTime())) return '—';
  try {
    return an.toLocaleString(dil, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return an.toISOString().slice(0, 16).replace('T', ' ');
  }
}

export function durumRengi(durum: string): string {
  switch (durum) {
    case 'bekliyor':
      return 'border-amber-400/30 bg-amber-500/10 text-amber-300';
    case 'kullanildi':
      return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300';
    case 'iptal':
      return 'border-white/15 bg-white/5 text-muted-foreground';
    case 'suresi_doldu':
      return 'border-red-400/30 bg-red-500/10 text-red-300';
    default:
      return 'border-white/10 bg-white/5 text-muted-foreground';
  }
}

type Ceviri = (anahtar: string, secenek?: Record<string, unknown>) => string;

/**
 * Başlığı seçili dilde kurar.
 *
 * Sunucunun `baslik` alanı e-posta için Türkçe yazılıyor (aşama adı,
 * "kredi" gibi). Ayrıntıda yapısal alanlar varsa başlık onlardan, yoksa
 * sunucunun metni olduğu gibi.
 */
export function yerelBaslik(
  islem: { tur: string; baslik: string; ayrinti?: IslemAyrintisi },
  t: Ceviri,
  dil: string,
): string {
  const a = islem.ayrinti || {};
  if (islem.tur === 'teslimat_onay' && a.proje && a.asama) {
    return `${a.proje} · ${t(`panel.asama.${a.asama}.ad`, { defaultValue: a.asama_etiketi || a.asama })}`;
  }
  if (islem.tur === 'teklif_kabul' && a.teklif_id != null && a.tutar != null) {
    const ne = a.paket || (a.ai_pm ? `AI vs PM ${a.ai_pm}` : a.kredi ? t('islem.krediPaketi', { sayi: a.kredi }) : '');
    return [`#${a.teklif_id}`, ne, tutarBicimle(a.tutar, a.para_birimi, dil)].filter(Boolean).join(' · ');
  }
  return islem.baslik;
}

/** Olumlu sonuç mu? (renk ve ikon için) */
export function olumluMu(sonuc?: string | null): boolean {
  return sonuc === 'kabul' || sonuc === 'onay' || sonuc === 'goruntulendi';
}
