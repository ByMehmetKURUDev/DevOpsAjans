import { AI_MODELI } from '@/lib/aiModel';
/**
 * Keşif Asistanı'nın yapay zekâ katmanı.
 *
 * Backend'de hazır duran `/api/v1/aihub/gentxt` uç noktasını kullanıyor;
 * anahtar tarayıcıya hiç inmiyor, istek sunucudan geçiyor.
 *
 * AI yapılandırılmamışsa (APP_AI_BASE_URL / APP_AI_KEY tanımsız) uç nokta
 * hata döner; çağıran taraf o durumda kural tabanlı öneriye düşer. Yani
 * asistan anahtar olmadan da çalışmaya devam eder, sadece metin üretmez.
 */

export interface KesifGirdisi {
  amac: string;
  serbest: string;
  kapsam: string[];
  zaman: string;
  butce: string;
  /** Paket adları — modelin uyduracağı isim yerine gerçek listeden seçmesi için. */
  paketler: string[];
  dil: string;
}

export interface KesifAnalizi {
  /** İki-üç cümlelik, ziyaretçinin kendi ihtiyacını özetleyen metin. */
  ozet: string;
  /** `paketler` dizisindeki indeks (0 tabanlı). */
  paketIndeksi: number;
  /** Paketin neden önerildiği, tek cümle. */
  gerekce: string;
  /** Somut sonraki adımlar, en çok dört madde. */
  adimlar: string[];
}


/** Modelden dönen metinden JSON bloğunu ayıklar (kod çiti gelirse de çalışır). */
function jsonAyikla(metin: string): unknown {
  const temiz = metin.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  const basla = temiz.indexOf('{');
  const bit = temiz.lastIndexOf('}');
  if (basla === -1 || bit === -1 || bit <= basla) throw new Error('JSON bulunamadi');
  return JSON.parse(temiz.slice(basla, bit + 1));
}

function analizDogrula(veri: unknown, paketSayisi: number): KesifAnalizi {
  const d = veri as Partial<Record<keyof KesifAnalizi, unknown>>;
  const ozet = typeof d.ozet === 'string' ? d.ozet.trim() : '';
  const gerekce = typeof d.gerekce === 'string' ? d.gerekce.trim() : '';
  const ham = Number(d.paketIndeksi);
  const paketIndeksi = Number.isInteger(ham) && ham >= 0 && ham < paketSayisi ? ham : -1;
  const adimlar = Array.isArray(d.adimlar)
    ? d.adimlar.filter((x): x is string => typeof x === 'string' && x.trim() !== '').slice(0, 4)
    : [];

  if (!ozet || paketIndeksi === -1) throw new Error('Analiz eksik dondu');
  return { ozet, paketIndeksi, gerekce, adimlar };
}

/**
 * Cevapları modele gönderir ve yapılandırılmış bir analiz ister.
 *
 * Hata durumunda istisna fırlatır — çağıran taraf kural tabanlı öneriye
 * düşmekle yükümlü. Sessizce boş sonuç dönmüyoruz ki hata fark edilsin.
 */
export async function kesifAnaliziIste(
  girdi: KesifGirdisi,
  signal?: AbortSignal,
): Promise<KesifAnalizi> {
  const sistem = [
    'Sen bir dijital ajansin proje kesif asistanisin.',
    'Ziyaretcinin verdigi cevaplara bakarak ihtiyacini ozetle ve listedeki paketlerden BIRINI sec.',
    'Listede olmayan paket uydurma. Fiyat, sure veya sonuc taahhudu verme.',
    'Emin olmadigin teknik detayi yazma; ziyaretci teknik olmayabilir, sade konus.',
    `Yanitini ${girdi.dil} dilinde yaz.`,
    'SADECE su bicimde JSON dondur, baska hicbir sey yazma:',
    '{"ozet":"...","paketIndeksi":0,"gerekce":"...","adimlar":["...","..."]}',
    'ozet: en fazla 3 cumle. gerekce: tek cumle. adimlar: en fazla 4 kisa madde.',
  ].join('\n');

  const kullanici = [
    `Projenin amaci: ${girdi.amac || '(belirtilmedi)'}`,
    `Kendi anlatimi: ${girdi.serbest || '(yok)'}`,
    `Gereken ozellikler: ${girdi.kapsam.length ? girdi.kapsam.join(', ') : '(belirtilmedi)'}`,
    `Zaman: ${girdi.zaman || '(belirtilmedi)'}`,
    `Butce: ${girdi.butce || '(belirtilmedi)'}`,
    '',
    'Secilebilecek paketler (indeksleriyle):',
    ...girdi.paketler.map((p, i) => `${i}: ${p}`),
  ].join('\n');

  const yanit = await fetch('/api/v1/aihub/gentxt', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    signal,
    body: JSON.stringify({
      model: AI_MODELI,
      stream: false,
      temperature: 0.4,
      max_tokens: 700,
      messages: [
        { role: 'system', content: sistem },
        { role: 'user', content: kullanici },
      ],
    }),
  });

  if (!yanit.ok) {
    throw new Error(`aihub ${yanit.status}`);
  }

  const govde = (await yanit.json()) as { content?: unknown };
  if (typeof govde.content !== 'string') throw new Error('Beklenmeyen yanit');

  return analizDogrula(jsonAyikla(govde.content), girdi.paketler.length);
}
