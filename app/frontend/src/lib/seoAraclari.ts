import { getAPIBaseURL } from '@/lib/config';

/**
 * Ücretsiz SEO araçları (Faz 4S) — tipler ve uç çağrıları.
 *
 * Girişsiz sayfa: düz `fetch` (SDK kurulmuyor), 429 / 400 gibi kodlar
 * doğrudan okunuyor. Bulgular metin taşımıyor (`kod` + `deger`); cümleyi
 * ön yüz yedi dilde kuruyor (`seoAracSonuc.bulgu.<kod>`).
 *
 * Hedef sitenin metinleri (başlık, açıklama, robots.txt, JSON-LD…) yalnız
 * DÜZ METİN olarak çiziliyor — React metni kaçışlıyor; `dangerouslySetInnerHTML`
 * hiçbir yerde yok.
 *
 * Fetch yanıtının gövdesi her yolda tüketiliyor (Parti 9 kuralı: okunmayan
 * gövde tarayıcıda isteği açık bırakıyor).
 */

export type Seviye = 'hata' | 'uyari' | 'bilgi' | 'iyi';
export const SEVIYE_SIRASI: Seviye[] = ['hata', 'uyari', 'bilgi', 'iyi'];

export interface Bulgu {
  kontrol: string;
  kod: string;
  seviye: Seviye;
  deger?: unknown;
}

export interface AracSonucu {
  arac: string;
  url: string;
  son_url: string;
  durum: number | null;
  puan: number | null;
  ozet: Record<Seviye, number>;
  bulgular: Bulgu[];
  // Araca özel ham ölçümler (görünüm bileşenleri kendi alanlarını okuyor).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  veri: Record<string, any>;
  /**
   * "Sonucu e-postayla gönder": `acik` yalnız sunucuda e-posta kanalı (Resend/SMTP) varsa true;
   * `jeton` sonucun bellekteki kısa ömürlü kopyasını (30 dk, tek kullanım) işaret eder.
   */
  eposta?: { acik: boolean; jeton: string | null; pazarlama_izni_sor: boolean };
}

export class AracHatasi extends Error {
  durum: number;
  kod: string;

  constructor(durum: number, kod: string) {
    super(kod);
    this.durum = durum;
    this.kod = kod;
  }
}

async function istek<T>(yol: string, govde: unknown, signal?: AbortSignal): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(`${getAPIBaseURL()}${yol}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', accept: 'application/json' },
      body: JSON.stringify(govde),
      signal,
    });
  } catch (h) {
    if ((h as { name?: string })?.name === 'AbortError') throw h;
    throw new AracHatasi(0, 'ag');
  }
  let veri: unknown = null;
  try {
    veri = await yanit.json();
  } catch {
    veri = null;
  }
  if (!yanit.ok) {
    const detay = (veri as { detail?: { kod?: unknown } } | null)?.detail;
    const kod = detay && typeof detay === 'object' && typeof detay.kod === 'string' ? detay.kod : 'genel';
    throw new AracHatasi(yanit.status, kod);
  }
  return veri as T;
}

export function araciCalistir(
  slug: string,
  govde: { url: string; ajan?: string; kelime?: string },
  signal?: AbortSignal,
) {
  return istek<AracSonucu>(`/api/v1/seo-araclari/${encodeURIComponent(slug)}`, govde, signal);
}

/**
 * "Sonucu e-postayla gönder" (isteğe bağlı). Sonucun kendisi GÖNDERİLMİYOR, yalnız jeton:
 * e-postayı sunucu kendi ürettiği sonuçtan kuruyor. Ziyaretçi CRM'e aday olarak yazılıyor;
 * pazarlama izni ayrı kutu (yalnız `pazarlama_izni_sor` iken gösterilir, JSON true gider).
 * `web_sitesi` bal küpü: insan görmez, bot doldurur.
 */
export function sonucuEpostala(
  slug: string,
  govde: { jeton: string; eposta: string; ad?: string; pazarlama_izni: boolean; dil: string; web_sitesi?: string },
) {
  return istek<{ gonderildi: boolean }>(`/api/v1/seo-araclari/${encodeURIComponent(slug)}/eposta`, govde);
}

/** Yönetici özeti (Satış › Site analizleri › Ücretsiz SEO araçları). */
export interface AracOzetSatiri {
  arac: string;
  kullanim: number;
  hata: number;
  eposta: number;
  aday: number;
  tam_analiz: number;
  tam_analiz_aday: number;
  /** `gunler` ile aynı sırada, günlük çalıştırma sayısı. */
  gunluk: number[];
}

export interface AracYonetimOzeti {
  gun: number;
  gunler: string[];
  araclar: AracOzetSatiri[];
  toplam: { kullanim: number; hata: number; eposta: number; aday: number; tam_analiz: number; tam_analiz_aday: number };
  gunluk: number[];
}
