/**
 * Keşif Asistanı'nın yapay zekâ katmanı.
 *
 * Faz 3U: amaca özel `/api/v1/ai/kesif` ucu. Sistem istemi, model ve
 * `max_tokens` SUNUCUDA; buradan yalnız ziyaretçinin cevapları ve paket
 * adları (veri) gidiyor. Uç herkese açık ama IP başına ve günlük toplam
 * bütçeyle sınırlı (429).
 *
 * AI yapılandırılmamışsa, sınır dolmuşsa ya da yanıt bozuksa istisna
 * fırlatılır; çağıran taraf kural tabanlı öneriye düşer. Yani asistan
 * anahtar olmadan da çalışmaya devam eder, sadece metin üretmez.
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
  const yanit = await fetch('/api/v1/ai/kesif', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    signal,
    body: JSON.stringify({
      amac: girdi.amac.slice(0, 300),
      // Sunucu sınırı 2000 karakter; uzun anlatım kesilip gönderiliyor (422 yerine).
      serbest: girdi.serbest.slice(0, 2000),
      kapsam: girdi.kapsam.slice(0, 20),
      zaman: girdi.zaman,
      butce: girdi.butce,
      paketler: girdi.paketler,
      dil: girdi.dil,
    }),
  });

  if (!yanit.ok) {
    throw new Error(`kesif ${yanit.status}`);
  }

  const govde = (await yanit.json()) as { icerik?: unknown };
  if (typeof govde.icerik !== 'string') throw new Error('Beklenmeyen yanit');

  return analizDogrula(jsonAyikla(govde.icerik), girdi.paketler.length);
}
