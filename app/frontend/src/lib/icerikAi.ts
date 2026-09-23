import { AI_MODELI } from '@/lib/aiModel';
import { KANAL_SINIRI, type Kanal } from '@/lib/icerikPlani';

/**
 * Gönderi metni taslağı.
 *
 * İstek arka uçtaki `/api/v1/aihub/gentxt` ucuna gidiyor; anahtar
 * sunucuda duruyor. AI yapılandırılmamışsa uç hata dönüyor ve panel
 * bunu açıkça söylüyor — uydurma bir taslak göstermiyor.
 *
 * Modelin uyması gereken tek kural var ve tekrar edilmeye değer:
 * FİYAT VE SÜRE SÖZÜ YOK. Bir sosyal medya gönderisi "3 günde teslim"
 * derse bu bir taahhüt gibi okunuyor ve tutulmadığında güveni o bozuyor.
 * Aynı kural site asistanında da uygulanıyor.
 */

export interface TaslakGirdisi {
  konu: string;
  kanal: Kanal;
  /** Serbest yönlendirme: kampanya, hedef kitle, üslup. */
  yonlendirme?: string;
}

export async function icerikTaslagiUret(
  girdi: TaslakGirdisi,
  signal?: AbortSignal,
): Promise<string> {
  const sinir = KANAL_SINIRI[girdi.kanal];

  const sistem = [
    'Sen mehmetkuru.dev için sosyal medya metni yazan bir içerik yazarısın.',
    'Site web geliştirme, e-ticaret, SaaS ve dijital pazarlama hizmeti veriyor.',
    `Metni "${girdi.kanal}" kanalı için yaz.`,
    sinir ? `Toplam uzunluk ${sinir} karakteri GEÇMESİN.` : 'Metni gereksiz uzatma.',
    'ASLA fiyat, süre ya da teslim tarihi yazma; bunlar görüşmede netleşir.',
    'Uydurma müşteri adı, uydurma rakam, uydurma referans kullanma.',
    'Türkçe yaz. Abartılı pazarlama dili ve boş övgü kullanma; somut konuş.',
    'Yalnızca gönderinin kendisini döndür: açıklama, başlık etiketi ya da tırnak ekleme.',
    girdi.kanal === 'x'
      ? 'Hashtag kullanma; X’te yer israfı.'
      : 'En fazla 3 hashtag, metnin sonunda.',
  ].join('\n');

  const kullanici = [
    `Konu: ${girdi.konu}`,
    girdi.yonlendirme?.trim() ? `Ek yönlendirme: ${girdi.yonlendirme.trim()}` : '',
  ]
    .filter(Boolean)
    .join('\n');

  const yanit = await fetch('/api/v1/aihub/gentxt', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    signal,
    body: JSON.stringify({
      model: AI_MODELI,
      stream: false,
      temperature: 0.8,
      max_tokens: 700,
      messages: [
        { role: 'system', content: sistem },
        { role: 'user', content: kullanici },
      ],
    }),
  });

  if (!yanit.ok) throw new Error(`AI ucu ${yanit.status} döndü`);
  const govde = (await yanit.json()) as { content?: string };
  const metin = (govde?.content || '').trim();
  if (!metin) throw new Error('AI boş yanıt döndü');
  return metin;
}
