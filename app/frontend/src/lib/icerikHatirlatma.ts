import { client } from '@/lib/sdkClient';

/**
 * Geciken içerik gönderileri için hatırlatma e-postası.
 *
 * İstek üzerine gönderiliyor, zamanlanmış iş yok: sunucu ücretsiz
 * katmanda uykuya geçtiği için saat başı çalışacak bir iş tam saatinde
 * çalışmıyor. Sessizce çalışmayan hatırlatma, hiç olmamasından kötü —
 * insan ona güvenip bakmayı bırakıyor.
 *
 * Uç yöneticiye açık; adresler panelde `admin_emails` altında duruyor.
 */

export interface HatirlatmaSonucu {
  /** Zamanı geçmiş gönderi sayısı. */
  geciken: number;
  /** E-posta kanalı ne yaptı: sent | skipped | failed | off | unknown */
  epostaDurumu: string;
  epostaAyrinti: string;
  /** Kısayol: yalnızca "sent" ise gerçekten gitti. */
  epostaGitti: boolean;
  /** Kaç yönetici adresine gönderildi. */
  aliciSayisi: number;
  /** Gönderilen metin; gitmediyse elden yollanabilir. */
  metin: string;
}

interface HamYanit {
  geciken?: number;
  eposta_durumu?: string;
  eposta_ayrinti?: string;
  alici_sayisi?: number;
  metin?: string;
}

export async function hatirlatmaGonder(): Promise<HatirlatmaSonucu> {
  const yanit = (await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/content-reminder',
    data: {},
  })) as unknown;

  // SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz.
  const govde = (
    yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)
      ? (yanit as { data: unknown }).data
      : yanit
  ) as HamYanit | undefined;

  const durum = govde?.eposta_durumu || 'unknown';
  return {
    geciken: govde?.geciken ?? 0,
    epostaDurumu: durum,
    epostaAyrinti: govde?.eposta_ayrinti || '',
    epostaGitti: durum === 'sent',
    aliciSayisi: govde?.alici_sayisi ?? 0,
    metin: govde?.metin || '',
  };
}
