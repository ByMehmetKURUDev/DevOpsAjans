import { client } from '@/lib/sdkClient';
import type { Kanal } from '@/lib/icerikPlani';

/**
 * Gönderi metni taslağı.
 *
 * Faz 3U: yalnız yöneticiye açık, amaca özel `/api/v1/ai/icerik-taslagi`
 * ucu. Sistem istemi (kanal sınırı, hashtag kuralı…), model ve
 * `max_tokens` SUNUCUDA; buradan yalnız konu, kanal ve yönlendirme gidiyor.
 * AI yapılandırılmamışsa uç hata dönüyor ve panel bunu açıkça söylüyor —
 * uydurma bir taslak göstermiyor.
 *
 * Modelin uyması gereken tek kural var ve tekrar edilmeye değer:
 * FİYAT VE SÜRE SÖZÜ YOK. Bir sosyal medya gönderisi "3 günde teslim"
 * derse bu bir taahhüt gibi okunuyor ve tutulmadığında güveni o bozuyor.
 * Aynı kural site asistanında da uygulanıyor (ikisi de sunucuda).
 */

export interface TaslakGirdisi {
  konu: string;
  kanal: Kanal;
  /** Serbest yönlendirme: kampanya, hedef kitle, üslup. */
  yonlendirme?: string;
}

function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

export async function icerikTaslagiUret(girdi: TaslakGirdisi): Promise<string> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/ai/icerik-taslagi',
    data: {
      konu: girdi.konu.slice(0, 500),
      kanal: girdi.kanal,
      yonlendirme: (girdi.yonlendirme || '').trim().slice(0, 1500),
    },
  });
  const govde = govdeyiAc<{ icerik?: string }>(yanit);
  const metin = (govde?.icerik || '').trim();
  if (!metin) throw new Error('AI boş yanıt döndü');
  return metin;
}
