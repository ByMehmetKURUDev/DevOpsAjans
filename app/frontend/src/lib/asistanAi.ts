/**
 * Site asistanının dil modeli katmanı.
 *
 * Faz 3U: amaca özel `/api/v1/ai/asistan` ucu. Çerçeve (sistem istemi:
 * fiyat/süre sözü yok, paket uydurma yok…), model ve `max_tokens`
 * SUNUCUDA; buradan yalnız konuşma ve paket adları (veri) gidiyor. Uç
 * herkese açık ama IP başına ve günlük toplam bütçeyle sınırlı (429).
 *
 * AI yapılandırılmamışsa ya da sınır dolmuşsa uç hata dönüyor ve arayüz
 * bunu açıkça gösteriyor — uydurma bir cevap üretmiyor.
 */

import { govdeyiTuket } from '@/lib/yanit';

export interface Mesaj {
  rol: 'kullanici' | 'asistan';
  metin: string;
}

/** Sunucunun bir mesaj için kabul ettiği en uzun metin. */
export const MESAJ_SINIRI = 2000;

/** Sunucu hatası; `yogun` = hız sınırı ya da günlük bütçe (429). */
export class AsistanHatasi extends Error {
  constructor(public durum: number) {
    super(`asistan ${durum}`);
  }
  get yogun(): boolean {
    return this.durum === 429;
  }
}

export async function asistanaSor(
  girdi: { gecmis: Mesaj[]; paketler: string[]; dil: string },
  signal?: AbortSignal,
): Promise<string> {
  const yanit = await fetch('/api/v1/ai/asistan', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    signal,
    body: JSON.stringify({
      // Son 8 tur yeterli (sunucu da yalnız sonuncuları kullanıyor).
      mesajlar: girdi.gecmis.slice(-8).map((m) => ({ rol: m.rol, metin: m.metin.slice(0, MESAJ_SINIRI) })),
      paketler: girdi.paketler,
      dil: girdi.dil,
    }),
  });

  if (!yanit.ok) {
    await govdeyiTuket(yanit);
    throw new AsistanHatasi(yanit.status);
  }

  const govde = (await yanit.json()) as { icerik?: unknown };
  const metin = typeof govde.icerik === 'string' ? govde.icerik.trim() : '';
  if (!metin) throw new Error('Beklenmeyen yanit');
  return metin;
}
