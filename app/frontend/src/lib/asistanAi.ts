/**
 * Site asistanının dil modeli katmanı.
 *
 * İstek arka uçtaki `/api/v1/aihub/gentxt` ucuna gidiyor; anahtar sunucuda
 * duruyor, tarayıcıya hiç inmiyor. AI yapılandırılmamışsa uç hata dönüyor
 * ve arayüz bunu açıkça gösteriyor — uydurma bir cevap üretmiyor.
 */

/** Sağlayıcı değişirse tek satır: `kesifAi.ts` ile aynı model. */
const MODEL = 'claude-sonnet-4.6';

export interface Mesaj {
  rol: 'kullanici' | 'asistan';
  metin: string;
}

/**
 * Modele verilen çerçeve.
 *
 * Fiyat ve süre sözü vermesi bilerek yasak: model "iki haftada biter"
 * derse bu bir taahhüt gibi okunur ve tutulamazsa güveni o bozar. Paket
 * adlarını da uydurmuyor — listede ne varsa onu söylüyor.
 */
function sistemMetni(paketler: string[], dil: string): string {
  return [
    'Sen mehmetkuru.dev sitesinin proje danışmanı asistanısın.',
    'Ziyaretçi bir yazılım, web ya da e-ticaret projesi düşünüyor; kapsamı netleştirmesine yardım et.',
    'Kısa ve somut konuş: en fazla 4-5 cümle. Gerekiyorsa sonunda tek bir soru sor.',
    'ASLA fiyat, süre ya da teslim tarihi sözü verme; bunların görüşmede netleştiğini söyle.',
    'Paket önerirken yalnızca şu listeden seç, yeni paket uydurma:',
    ...paketler.map((p, i) => `${i + 1}. ${p}`),
    'Site ücretsiz keşif görüşmesi sunuyor; uygun düştüğünde iletişim sayfasına yönlendir.',
    `Yanıtı şu dilde yaz: ${dil}.`,
    'Düz metin yaz; markdown başlık, tablo ya da kod bloğu kullanma.',
  ].join('\n');
}

export async function asistanaSor(
  girdi: { gecmis: Mesaj[]; paketler: string[]; dil: string },
  signal?: AbortSignal,
): Promise<string> {
  const yanit = await fetch('/api/v1/aihub/gentxt', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    signal,
    body: JSON.stringify({
      model: MODEL,
      stream: false,
      temperature: 0.5,
      max_tokens: 500,
      messages: [
        { role: 'system', content: sistemMetni(girdi.paketler, girdi.dil) },
        // Son 8 tur yeterli: daha uzun geçmiş hem pahalı hem konuyu dağıtıyor.
        ...girdi.gecmis.slice(-8).map((m) => ({
          role: m.rol === 'kullanici' ? 'user' : 'assistant',
          content: m.metin,
        })),
      ],
    }),
  });

  if (!yanit.ok) throw new Error(`aihub ${yanit.status}`);

  const govde = (await yanit.json()) as { content?: unknown };
  const metin = typeof govde.content === 'string' ? govde.content.trim() : '';
  if (!metin) throw new Error('Beklenmeyen yanit');
  return metin;
}
