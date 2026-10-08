/**
 * Kaynaklar — sitedeki herkese açık araç/beceri listesi (Faz 3K).
 *
 * Veri üç yerden gelebiliyor, sırasıyla:
 *  1. Sayfaya gömülü veri (`<script id="kaynak-verisi">`): prerender HTML'i
 *     hangi veriyle çizildiyse o. Doğrudan açılan sayfa ilk çizimini ağ
 *     beklemeden yapıyor — ücretsiz sunucu uykudaysa ilk istek yarım dakika
 *     sürebiliyor, prerender içeriği bu sürede silinip yükleniyor göstergesi
 *     çıkmasın.
 *  2. Bellek önbelleği (aynı oturumda liste → ayrıntı → liste gezinmesi).
 *  3. API (`/api/v1/kaynaklar`): her açılışta arka planda tazeleniyor;
 *     panelde yeni eklenen kaynak prerender'ı beklemeden görünüyor.
 *
 * `fetch` doğrudan: uç girişsiz ve aynı origin'de; SDK gerekmiyor.
 */

import { govdeyiTuket } from '@/lib/yanit';

export interface KaynakOzeti {
  slug: string;
  kategori: string;
  baslik: string;
  ozet: string;
  etiketler: string[];
  ucretsiz: boolean;
  acik_kaynak: boolean;
  youtube_short: string | null;
  one_cikan: boolean;
  sira: number;
  baglanti_turu: string;
}

export interface KaynakAyrintisi extends KaynakOzeti {
  aciklama: string;
  adimlar: string[];
  baglanti: string;
  lisans: string | null;
  kategori_adi: string;
  dogrulama_tarihi: string | null;
  updated_at: string | null;
}

export interface KaynakKategorisi {
  anahtar: string;
  ad: string;
  sayi: number;
}

export interface KaynakListesi {
  dil: string;
  kaynaklar: KaynakOzeti[];
  kategoriler: KaynakKategorisi[];
  toplam: number;
}

export interface KaynakDetayi {
  dil: string;
  kaynak: KaynakAyrintisi;
  ilgili: KaynakOzeti[];
}

/** Prerender'ın sayfaya gömdüğü veri. `detay: null` → bilinmeyen slug. */
export interface GomuluKaynakVerisi {
  yol: string;
  dil: string;
  liste?: KaynakListesi;
  detay?: KaynakDetayi | null;
}

const GOMULU_KIMLIK = 'kaynak-verisi';

/** Sondaki eğik çizgiyi atar (kök hariç) — prerender ile istemci aynı biçimi karşılaştırsın. */
export function yoluSadelestir(yol: string): string {
  const temiz = yol.split(/[?#]/)[0].replace(/\/+$/, '');
  return temiz || '/';
}

let gomulu: GomuluKaynakVerisi | null | undefined;

/** Prerender: her sayfa çiziminden önce o sayfanın verisi (diğer sayfalarda null). */
export function gomuluVeriyiAyarla(veri: GomuluKaynakVerisi | null): void {
  gomulu = veri;
}

function gomuluVeri(): GomuluKaynakVerisi | null {
  if (gomulu !== undefined) return gomulu;
  gomulu = null;
  if (typeof document === 'undefined') return gomulu;
  const el = document.getElementById(GOMULU_KIMLIK);
  if (el?.textContent) {
    try {
      gomulu = JSON.parse(el.textContent) as GomuluKaynakVerisi;
    } catch {
      gomulu = null;
    }
  }
  return gomulu;
}

/** Tarayıcıda mı? Prerender'da (Node) önbellek tutulmuyor: her sayfa kendi verisiyle. */
const tarayicida = typeof window !== 'undefined';
const listeler = new Map<string, KaynakListesi>();
const detaylar = new Map<string, KaynakDetayi>();

/** İlk çizim için eldeki liste (gömülü ya da önbellek); yoksa null. */
export function eldekiListe(yol: string, dil: string): KaynakListesi | null {
  const g = gomuluVeri();
  if (g?.liste && g.dil === dil && yoluSadelestir(g.yol) === yoluSadelestir(yol)) {
    if (tarayicida && !listeler.has(dil)) listeler.set(dil, g.liste);
    return g.liste;
  }
  return listeler.get(dil) ?? null;
}

/**
 * İlk çizim için eldeki ayrıntı. `undefined`: bilinmiyor (yükle);
 * `null`: prerender bu slug'ı tanımıyor (yine de API'ye sorulur).
 */
export function eldekiDetay(yol: string, slug: string, dil: string): KaynakDetayi | null | undefined {
  const g = gomuluVeri();
  if (g && 'detay' in g && g.dil === dil && yoluSadelestir(g.yol) === yoluSadelestir(yol)) {
    if (g.detay && tarayicida && !detaylar.has(`${dil}:${slug}`)) detaylar.set(`${dil}:${slug}`, g.detay);
    return g.detay ?? null;
  }
  return detaylar.get(`${dil}:${slug}`);
}

/** Listeden geçilen ayrıntı sayfası, ayrıntı gelene kadar kartı gösterebilsin. */
export function listedekiOzet(slug: string, dil: string): KaynakOzeti | null {
  return listeler.get(dil)?.kaynaklar.find((k) => k.slug === slug) ?? null;
}

export class KaynakBulunamadi extends Error {}

async function getir<T>(adres: string, signal?: AbortSignal): Promise<T> {
  const yanit = await fetch(adres, { headers: { accept: 'application/json' }, signal });
  if (!yanit.ok) {
    await govdeyiTuket(yanit);
    if (yanit.status === 404) throw new KaynakBulunamadi('bulunamadi');
    throw new Error(`HTTP ${yanit.status}`);
  }
  return (await yanit.json()) as T;
}

export async function listeyiGetir(dil: string, signal?: AbortSignal): Promise<KaynakListesi> {
  const liste = await getir<KaynakListesi>(`/api/v1/kaynaklar?dil=${encodeURIComponent(dil)}`, signal);
  const temiz: KaynakListesi = {
    dil,
    kaynaklar: Array.isArray(liste?.kaynaklar) ? liste.kaynaklar : [],
    kategoriler: Array.isArray(liste?.kategoriler) ? liste.kategoriler : [],
    toplam: liste?.toplam ?? 0,
  };
  listeler.set(dil, temiz);
  return temiz;
}

export async function detayiGetir(slug: string, dil: string, signal?: AbortSignal): Promise<KaynakDetayi> {
  const detay = await getir<KaynakDetayi>(
    `/api/v1/kaynaklar/${encodeURIComponent(slug)}?dil=${encodeURIComponent(dil)}`,
    signal,
  );
  detaylar.set(`${dil}:${slug}`, detay);
  return detay;
}

/** Arama için: küçük harf, Türkçe İ/ı, aksansız (arka uçla aynı kural). */
export function aramaIcinSadelestir(metin: string): string {
  return (metin || '')
    .replace(/İ/g, 'i')
    .replace(/I/g, 'ı')
    .toLowerCase()
    .replace(/ı/g, 'i')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '');
}

/** Her kelime başlık/özet/etiket/kategori adı/slug içinde geçmeli. */
export function aramayaUyar(k: KaynakOzeti, kelimeler: string[], kategoriAdi: string): boolean {
  if (kelimeler.length === 0) return true;
  const havuz = aramaIcinSadelestir([k.baslik, k.ozet, k.slug, kategoriAdi, ...k.etiketler].join(' '));
  return kelimeler.every((w) => havuz.includes(w));
}
