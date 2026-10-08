import type { TFunction } from 'i18next';

import { client } from '@/lib/sdkClient';

/**
 * Faz 4W — otomasyon kuralları ("şu olunca bunu yap") ve özel alanlar.
 *
 * Yönetici `/api/v1/otomasyon/yonetim/...`, müşteri `/api/v1/otomasyonlarim/...` (etkin
 * hesap `X-MK-Hesap` başlığıyla — istek katmanı ekliyor). İki panel aynı bileşeni
 * kullanıyor; yalnız taban yol değişiyor. Özel alan tanımları yalnız ajansta
 * (`/api/v1/ozel-alanlar/yonetim`), müşteri görünür alanları salt okunur alır
 * (`/api/v1/ozel-alanlarim/<varlik>/<id>`).
 *
 * Bu dosya yalnız Otomasyon sekmesi ya da özel alan bölümü açıldığında (lazy parçada) iniyor.
 */

export type OtoMod = 'yonetici' | 'musteri';

export interface SemaAlani {
  yol: string;
  tur: 'metin' | 'sayi' | 'tarih' | 'liste' | 'evet_hayir';
  degisir: boolean;
  ozel?: boolean;
  ad?: string;
  secenekler?: string[];
}

export interface OlayTanimi {
  anahtar: string;
  nesneler: string[];
  proje_var: boolean;
  sema: SemaAlani[];
}

export interface Kosul {
  alan: string;
  islec: string;
  deger?: string | null;
}

export interface KosulGrubu {
  baglac: 've' | 'veya';
  kosullar: Kosul[];
}

export type EylemTuru =
  | 'eposta'
  | 'bildirim'
  | 'gorev'
  | 'crm_asama'
  | 'crm_etiket'
  | 'crm_sahip'
  | 'crm_aktivite'
  | 'destek'
  | 'webhook'
  | 'bekle';

export interface Eylem {
  tur: EylemTuru;
  [alan: string]: unknown;
}

export interface Sablon {
  anahtar: string;
  tetik: string;
  kosullar: KosulGrubu;
  eylemler: Eylem[];
  metinler: Record<string, string>;
}

export interface OtoMeta {
  sahip_tur: 'ajans' | 'musteri';
  olaylar: OlayTanimi[];
  islecler: string[];
  degersiz_islecler: string[];
  eylemler: EylemTuru[];
  oncelikler: string[];
  aktivite_turleri: string[];
  bekleme_birimleri: string[];
  sablonlar: Sablon[];
  sinirlar: { kural: number; kural_sayisi: number; eylem: number; kosul: number; derinlik: number; dakika: number; saat: number; saklama_gun: number };
  webhook_uclari: { id: number; url: string; aktif: boolean; aciklama: string | null }[];
  projeler: { id: number; baslik: string; hesap: string | null }[];
  ekip?: string[];
  crm_asamalari?: { anahtar: string; ad: string | null; ceviriler?: Record<string, { ad?: string }> | null }[];
  /** Faz 6R (yalnız müşteri): hesaba uygulanan sektör setinin önerdiği şablonlar (kurulmaz, işaretlenir). */
  onerilen_sablonlar?: string[];
}

export interface Kural {
  id: number;
  sahip_tur: 'ajans' | 'musteri';
  hesap_email: string | null;
  ad: string;
  aciklama: string | null;
  aktif: boolean;
  tetik: string;
  kosullar: KosulGrubu;
  eylemler: Eylem[];
  sablon: string | null;
  olusturan: string | null;
  /** Faz 7H: "bekle"den sonra koşullar kaydın güncel hâliyle yeniden denetlenir (eski kurallarda false). */
  bekleme_sonrasi_denetim: boolean;
  calisma_sayisi: number;
  son_calisma_at: string | null;
  olusturma: string | null;
  guncelleme: string | null;
}

export interface KuralGirdisi {
  ad: string;
  aciklama?: string | null;
  aktif?: boolean;
  bekleme_sonrasi_denetim?: boolean;
  tetik: string;
  kosullar: KosulGrubu;
  eylemler: Eylem[];
}

export interface EylemSonucu {
  sira: number;
  tur: string;
  durum: 'basarili' | 'atlandi' | 'hata' | 'bekliyor' | 'yapilacak' | 'atlanacak';
  neden?: string;
  ozet?: Record<string, unknown>;
}

export interface KosulAyrintisi {
  alan: string;
  islec: string;
  deger: string | null;
  gercek: unknown;
  sonuc: boolean;
}

export interface Calisma {
  id: number;
  kural_id: number;
  kural: string | null;
  olay_id: string;
  tur: string;
  olay_hesap: string | null;
  durum: 'bekliyor' | 'tamam' | 'hata' | 'kosul_tutmadi' | 'atlandi';
  neden: string | null;
  derinlik: number;
  kosul_sonucu: boolean | null;
  kosul_ayrinti: KosulAyrintisi[];
  eylem_sonuclari: EylemSonucu[];
  sonraki_eylem: number;
  sonraki_zaman: string | null;
  veri: Record<string, unknown>;
  olusturma: string | null;
  bitis: string | null;
}

export interface KuruSonuc {
  kosul_sonucu: boolean;
  kosul_ayrinti: KosulAyrintisi[];
  eylemler: EylemSonucu[];
  baglam: Record<string, unknown>;
  kaynak: 'ornek' | 'elle' | 'olay';
  bilinmeyen_degiskenler: string[];
}

export class OtoHatasi extends Error {
  constructor(
    public durum: number,
    public kod: string,
    public ek: Record<string, unknown> = {}
  ) {
    super(kod);
  }
}

function hataCoz(durum: number, detay: unknown): OtoHatasi {
  if (detay && typeof detay === 'object' && typeof (detay as { kod?: unknown }).kod === 'string') {
    const { kod, ...ek } = detay as { kod: string } & Record<string, unknown>;
    return new OtoHatasi(durum, kod, ek);
  }
  if (durum === 429) return new OtoHatasi(durum, 'cok_hizli');
  if (durum === 404) return new OtoHatasi(durum, 'bulunamadi');
  return new OtoHatasi(durum, durum === 0 ? 'ag' : 'genel');
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

async function istek<T>(method: string, url: string, data?: unknown): Promise<T> {
  try {
    const yanit = await client.apiCall.invoke({ method, url, data: data as Record<string, unknown> | undefined });
    return govdeyiAc<T>(yanit) as T;
  } catch (hata) {
    const h = hata as { status?: number; response?: { status?: number; data?: { detail?: unknown } } };
    throw hataCoz(h?.response?.status ?? h?.status ?? 0, h?.response?.data?.detail);
  }
}

export function otomasyonApi(mod: OtoMod) {
  const taban = mod === 'yonetici' ? '/api/v1/otomasyon/yonetim' : '/api/v1/otomasyonlarim';
  return {
    meta: () => istek<OtoMeta>('GET', `${taban}/meta`),
    ornekBaglam: async (tetik: string) =>
      (await istek<{ baglam: Record<string, unknown> }>('GET', `${taban}/ornek-baglam?tetik=${encodeURIComponent(tetik)}`))?.baglam ?? {},
    kurallar: async () => (await istek<{ items: Kural[] }>('GET', `${taban}/kurallar`))?.items ?? [],
    olustur: (g: KuralGirdisi) => istek<Kural>('POST', `${taban}/kurallar`, g),
    sablondan: (sablon: string, metinler?: Record<string, string>) =>
      istek<Kural>('POST', `${taban}/kurallar/sablondan`, { sablon, metinler }),
    guncelle: (id: number, g: Partial<KuralGirdisi>) => istek<Kural>('PUT', `${taban}/kurallar/${id}`, g),
    sil: (id: number) => istek<{ silindi: boolean }>('DELETE', `${taban}/kurallar/${id}`),
    kayitliTest: (id: number, govde: { baglam?: Record<string, unknown>; calisma_id?: number } = {}) =>
      istek<KuruSonuc>('POST', `${taban}/kurallar/${id}/test`, govde),
    taslakTest: (kural: Partial<KuralGirdisi>, govde: { baglam?: Record<string, unknown>; calisma_id?: number } = {}) =>
      istek<KuruSonuc>('POST', `${taban}/test`, { kural, ...govde }),
    gunluk: (p: { kural_id?: number | null; durum?: string | null; once?: number | null } = {}) => {
      const q = new URLSearchParams({ limit: '30' });
      if (p.kural_id) q.set('kural_id', String(p.kural_id));
      if (p.durum) q.set('durum', p.durum);
      if (p.once) q.set('once', String(p.once));
      return istek<{ items: Calisma[]; sonraki: number | null }>('GET', `${taban}/gunluk?${q.toString()}`);
    },
  };
}

export type OtomasyonApi = ReturnType<typeof otomasyonApi>;

// ---------------------------------------------------------------------------
// Faz 7O — Sistem (yalnız yönetici): haftalık özet
// ---------------------------------------------------------------------------
export interface OzetSatiri {
  ad: string;
  ayrinti: string | null;
  tur: string | null;
  gun: number | null;
  tutar: number | null;
  para_birimi: string | null;
  zaman: string | null;
}

export interface OzetBolumu {
  anahtar: 'faturalar' | 'destek' | 'crm' | 'teklifler' | 'icerik' | 'belgeler' | 'yenilemeler' | 'siteler' | 'muhasebe';
  sekme: string;
  sayi: number;
  ek: {
    toplamlar?: { para_birimi: string; tutar: number }[];
    sla_asildi?: number;
    sonraki_adim?: number;
    hareketsiz?: number;
    geciken?: number;
    hata?: boolean;
    // Faz 6M — ön muhasebe: bütçe aşımı ve vadesi geçmiş alacağı olan cari sayısı.
    butce?: number;
    alacak?: number;
  };
  ornekler: OzetSatiri[];
}

export interface HaftalikOzet {
  hafta: string;
  olusturma: string;
  bos: boolean;
  bolumler: OzetBolumu[];
  eposta: { konu: string; metin: string };
}

export interface HaftalikOzetDurumu {
  acik: boolean;
  son_gonderim: string | null;
  hafta: string;
  bu_hafta: 'gonderildi' | 'bos' | 'bekliyor';
  sonraki: string | null;
  eposta_kanali: 'hazir' | 'kapali' | 'yapilandirilmadi' | null;
  alici_sayisi: number;
}

const SISTEM = '/api/v1/otomasyon/yonetim/haftalik-ozet';

export const sistemApi = {
  ozetDurumu: () => istek<HaftalikOzetDurumu>('GET', SISTEM),
  ozetOnizle: () => istek<HaftalikOzet>('GET', `${SISTEM}/onizle`),
  ozetAyarla: (acik: boolean) => istek<HaftalikOzetDurumu>('PUT', SISTEM, { acik }),
};

// ---------------------------------------------------------------------------
// Özel alanlar
// ---------------------------------------------------------------------------
export type OzelVarlik = 'crm_aday' | 'proje' | 'hesap' | 'destek';
export type OzelTur = 'metin' | 'sayi' | 'tarih' | 'secim' | 'coklu_secim' | 'evet_hayir' | 'url';

export interface OzelAlan {
  id: number;
  varlik: OzelVarlik;
  anahtar: string;
  ad: string;
  tur: OzelTur;
  secenekler: string[];
  zorunlu: boolean;
  sira: number;
  musteriye_gorunur: boolean;
  aktif: boolean;
}

export interface OzelAlanGirdisi {
  varlik?: OzelVarlik;
  ad?: string;
  anahtar?: string;
  tur?: OzelTur;
  secenekler?: string[];
  zorunlu?: boolean;
  sira?: number;
  musteriye_gorunur?: boolean;
  aktif?: boolean;
}

export interface OzelBolum {
  varlik: OzelVarlik;
  varlik_id: string;
  alanlar: OzelAlan[];
  degerler: Record<string, unknown>;
}

const OZ = '/api/v1/ozel-alanlar/yonetim';

export const ozelAlanApi = {
  liste: async (varlik?: OzelVarlik) =>
    (await istek<{ items: OzelAlan[]; turler: OzelTur[]; varliklar: OzelVarlik[]; gorunur_olabilir: OzelVarlik[]; form_turleri: OzelTur[] }>(
      'GET',
      `${OZ}${varlik ? `?varlik=${varlik}` : ''}`
    )),
  olustur: (g: OzelAlanGirdisi) => istek<OzelAlan>('POST', OZ, g),
  guncelle: (id: number, g: OzelAlanGirdisi) => istek<OzelAlan>('PUT', `${OZ}/${id}`, g),
  sil: (id: number) => istek<{ silindi: boolean }>('DELETE', `${OZ}/${id}`),
  bolum: (varlik: OzelVarlik, kimlik: string | number) =>
    istek<OzelBolum>('GET', `${OZ}/deger/${varlik}/${encodeURIComponent(String(kimlik))}`),
  kaydet: (varlik: OzelVarlik, kimlik: string | number, degerler: Record<string, unknown>) =>
    istek<OzelBolum>('PUT', `${OZ}/deger/${varlik}/${encodeURIComponent(String(kimlik))}`, { degerler }),
  musteriBolum: (varlik: 'proje' | 'destek', kimlik: number) => istek<OzelBolum>('GET', `/api/v1/ozel-alanlarim/${varlik}/${kimlik}`),
};

// ---------------------------------------------------------------------------
// Yardımcılar
// ---------------------------------------------------------------------------
/** i18n anahtarı için güvenli ad (`aday.ad` → `aday_ad`). */
export const anahtarAdi = (ad: string) => ad.replace(/[:.]/g, '_');

export function hataMetni(t: TFunction, e: unknown): string {
  if (e instanceof OtoHatasi) {
    const temel = t(`otomasyon.hata.${e.kod}`, { defaultValue: '' }) as string;
    const metin = temel || (t('otomasyon.hata.genel') as string);
    const alan = typeof e.ek.alan === 'string' ? ` (${e.ek.alan})` : '';
    const degisken = typeof e.ek.degisken === 'string' ? ` — {{${e.ek.degisken}}}` : '';
    return `${metin}${alan}${degisken}`;
  }
  return t('otomasyon.hata.genel');
}

export function ozelHataMetni(t: TFunction, e: unknown): string {
  if (e instanceof OtoHatasi) {
    const temel = t(`ozelAlanlar.hata.${e.kod}`, { defaultValue: '' }) as string;
    const alan = typeof e.ek.alan === 'string' ? ` (${e.ek.alan})` : '';
    return `${temel || t('ozelAlanlar.hata.genel')}${alan}`;
  }
  return t('ozelAlanlar.hata.genel');
}

/** Alan yolunun görünen adı: özel alanda alanın kendi adı, diğerlerinde çeviri. */
export function alanAdi(t: TFunction, a: SemaAlani | undefined, yol: string): string {
  if (a?.ozel && a.ad) return `${t(`otomasyon.nesne.${yol.split('.')[0]}`)} › ${a.ad}`;
  const [ns, ad] = yol.split('.');
  return `${t(`otomasyon.nesne.${ns}`)} › ${t(`otomasyon.alan.${ad}`, { defaultValue: ad })}`;
}

export function tarihYaz(iso: string | null | undefined, dil: string): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function bosEylem(tur: EylemTuru, ajans: boolean): Eylem {
  switch (tur) {
    case 'eposta':
      return { tur, nitelik: '', alici: 'kisi', konu: '', govde: '' };
    case 'bildirim':
      return { tur, alici: ajans ? 'yoneticiler' : 'hesap', baslik: '', govde: '' };
    case 'gorev':
      return { tur, proje: 'olay', baslik: '', son_tarih_gun: 3, oncelik: 'normal' };
    case 'crm_asama':
      return { tur, asama: '' };
    case 'crm_etiket':
      return { tur, islem: 'ekle', etiket: '' };
    case 'crm_sahip':
      return { tur, sorumlu: '' };
    case 'crm_aktivite':
      return { tur, aktivite_tur: 'not', metin: '' };
    case 'destek':
      return { tur, oncelik: '', etiket: '' };
    case 'webhook':
      return { tur, uc_id: null, etiket: '' };
    default:
      return { tur: 'bekle', miktar: 1, birim: 'saat' };
  }
}
