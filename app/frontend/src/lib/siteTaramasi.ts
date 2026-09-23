import { client } from '@/lib/sdkClient';

/**
 * Ajan tabanlı site taraması.
 *
 * Arka uç yayındaki siteyi bir bot gibi geziyor (sitemap → her sayfa →
 * sayfalardaki iç bağlantılar) ve bulduğu eksikleri döndürüyor. Tarayıcı
 * bunu kendisi yapamaz: başka bir kaynağa yapılan isteklerin gövdesini
 * CORS yüzünden okuyamaz, 404'ü de göremez.
 *
 * Tarama uzun sürebilir (onlarca istek), o yüzden çağıran taraf düğmeyi
 * kilitleyip bekletmeli.
 */

export type Seviye = 'hata' | 'uyari' | 'bilgi';

/**
 * Bulgu metni TAŞIMIYOR, kod taşıyor.
 *
 * Panel yedi dilde; arka uç hangi dilde bakıldığını bilmiyor ve
 * bilmemeli. Cümleyi `siteTarama.bulgu.<kod>` anahtarıyla panel kuruyor,
 * `deger` de sayıyı (karakter sayısı, milisaniye, adet) veriyor.
 */
export interface Bulgu {
  kod: string;
  seviye: Seviye;
  deger?: number | null;
}

/** Taramanın kendisiyle ilgili açıklama (tavana takılma, sitemap yok…). */
export interface Not {
  kod: string;
  deger?: number | null;
  tavan?: number | null;
}

export interface SayfaRaporu {
  url: string;
  durum: number;
  sure_ms: number;
  boyut: number;
  baslik: string;
  bulgular: Bulgu[];
}

export interface KirikBaglanti {
  url: string;
  durum: number;
  kaynaklar: string[];
}

export interface TaramaRaporu {
  site: string;
  sayfa_sayisi: number;
  baglanti_sayisi: number;
  sure_ms: number;
  ozet: Record<string, number>;
  sayfalar: SayfaRaporu[];
  kirik_baglantilar: KirikBaglanti[];
  notlar: Not[];
}

export async function taramayiCalistir(): Promise<TaramaRaporu> {
  const yanit = (await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/site-scan',
    data: {},
  })) as unknown;

  // SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz.
  const govde = (
    yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)
      ? (yanit as { data: unknown }).data
      : yanit
  ) as Partial<TaramaRaporu> | undefined;

  if (!govde || !Array.isArray(govde.sayfalar)) {
    throw new Error('Tarama sonucu okunamadı.');
  }

  return {
    site: govde.site || '',
    sayfa_sayisi: govde.sayfa_sayisi || 0,
    baglanti_sayisi: govde.baglanti_sayisi || 0,
    sure_ms: govde.sure_ms || 0,
    ozet: govde.ozet || {},
    sayfalar: govde.sayfalar,
    kirik_baglantilar: govde.kirik_baglantilar || [],
    notlar: govde.notlar || [],
  };
}
