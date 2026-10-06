/**
 * Modül vitrini (Faz 4V) — derleme verisini yükler (yalnız Node: vite.config ve betikler).
 *
 * Yapı her zaman depodaki kopyadan (`prerender/modul-vitrini-veri.json`) —
 * kayıttan üretilmiş, testle eşitliği denetlenen dosya; derleme sunucuya bağlı
 * kalmıyor, ayrıntı sayfaları her derlemede üretiliyor.
 *
 * Fiyat canlı uçtan: `https://mehmetkuru.dev/api/v1/modul-vitrini` (5 sn).
 * Ulaşılamazsa (uyuyan sunucu, ağ yok, uç henüz yayında değil) fiyatsız devam:
 * sayfa "pakete dahil" yazar, tutarı açılışta API'den tamamlar; JSON-LD'ye
 * `offers` girmez. Derleme hiçbir koşulda düşmez.
 *
 * `MODUL_VITRINI_KAYNAGI=yok` canlı isteği atlar (yerel/çevrimdışı derleme);
 * başka bir değer canlı adresin yerine geçer.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const kok = path.dirname(fileURLToPath(import.meta.url));
export const YAPI_YOLU = path.resolve(kok, 'modul-vitrini-veri.json');
const CANLI_ADRES = 'https://mehmetkuru.dev/api/v1/modul-vitrini';
const ZAMAN_ASIMI_MS = 5000;

export function vitrinYapisiniOku() {
  try {
    const veri = JSON.parse(fs.readFileSync(YAPI_YOLU, 'utf8'));
    if (Array.isArray(veri?.moduller) && Array.isArray(veri?.paketler)) return veri;
  } catch (hata) {
    console.warn(`[moduller] Yapı dosyası okunamadı (${hata?.message ?? hata}).`);
  }
  return { moduller: [], paketler: [], kategoriler: [], yakinda: [], temeller: [], olcekler: [] };
}

function fiyatlarGecerliMi(f) {
  return Boolean(f) && typeof f === 'object' && !Array.isArray(f);
}

let onbellek = null;

/** `{ fiyatlar, kaynak: 'canli' | 'yok' }` */
export async function vitrinFiyatlariniYukle() {
  if (onbellek) return onbellek;
  const ayar = (process.env.MODUL_VITRINI_KAYNAGI || '').trim();
  if (ayar !== 'yok') {
    const kesici = new AbortController();
    const zaman = setTimeout(() => kesici.abort(), ZAMAN_ASIMI_MS);
    try {
      const yanit = await fetch(ayar || CANLI_ADRES, { headers: { accept: 'application/json' }, signal: kesici.signal });
      if (!yanit.ok) throw new Error(`HTTP ${yanit.status}`);
      const veri = await yanit.json();
      if (!fiyatlarGecerliMi(veri?.fiyatlar)) throw new Error('beklenmeyen biçim');
      console.log(`[moduller] Fiyatlar canlı uçtan okundu: ${Object.keys(veri.fiyatlar).length} ölçek.`);
      onbellek = { fiyatlar: veri.fiyatlar, kaynak: 'canli' };
      return onbellek;
    } catch (hata) {
      console.warn(`[moduller] Fiyatlar okunamadı (${hata?.message ?? hata}) — vitrin fiyatsız üretilecek.`);
    } finally {
      clearTimeout(zaman);
    }
  }
  onbellek = { fiyatlar: {}, kaynak: 'yok' };
  return onbellek;
}

const SANAL_KIMLIK = 'virtual:modul-vitrini-fiyat';
const COZULMUS_KIMLIK = '\0virtual:modul-vitrini-fiyat';

/**
 * Vite eklentisi: derlemede okunan fiyatları `virtual:modul-vitrini-fiyat`
 * modülü olarak yalnız prerender betiğine verir (istemci içe aktarmıyor).
 */
export function vitrinFiyatEklentisi(fiyatlar) {
  return {
    name: 'mk-modul-vitrini-fiyat',
    resolveId(kimlik) {
      return kimlik === SANAL_KIMLIK ? COZULMUS_KIMLIK : null;
    },
    load(kimlik) {
      if (kimlik !== COZULMUS_KIMLIK) return null;
      return `export default ${JSON.stringify(fiyatlarGecerliMi(fiyatlar) ? fiyatlar : {})};`;
    },
  };
}
