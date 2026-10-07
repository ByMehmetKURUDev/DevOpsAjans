/**
 * Modül vitrini (Faz 4V) — derleme verisini yükler (yalnız Node: vite.config ve betikler).
 *
 * Yapı her zaman depodaki kopyadan (`prerender/modul-vitrini-veri.json`) —
 * kayıttan üretilmiş, testle eşitliği denetlenen dosya; derleme sunucuya bağlı
 * kalmıyor, ayrıntı sayfaları her derlemede üretiliyor.
 *
 * Fiyat sırasıyla (Faz 6R):
 *  1. Canlı uç `https://mehmetkuru.dev/api/v1/modul-vitrini` — 20 sn zaman aşımı,
 *     2 yeniden deneme (1 sn, 3 sn arayla): Render uykudan uyanırken ilk istek
 *     düşebiliyor, Cloudflare derleme ağı yavaş olabiliyor.
 *  2. Depodaki fiyat anlık görüntüsü `prerender/modul-vitrini-fiyat.json` —
 *     fiyatlandırma v5 tohumundan, sunucusuz üretilmiş (`python -m
 *     scripts.modul_vitrini_tohum`; test `hesapla` ile tutarlı olduğunu denetliyor).
 *  3. İkisi de yoksa fiyatsız: sayfa "pakete dahil" yazar, tutarı açılışta API'den
 *     tamamlar; JSON-LD'ye `offers` girmez. Derleme hiçbir koşulda düşmez.
 *
 * `MODUL_VITRINI_KAYNAGI=yok` canlı isteği atlar (yerel/çevrimdışı derleme →
 * anlık görüntü); başka bir değer canlı adresin yerine geçer.
 * `MODUL_VITRINI_ANLIK=yok` anlık görüntüyü de kapatır (fiyatsız derleme denemesi).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const kok = path.dirname(fileURLToPath(import.meta.url));
export const YAPI_YOLU = path.resolve(kok, 'modul-vitrini-veri.json');
export const ANLIK_YOLU = path.resolve(kok, 'modul-vitrini-fiyat.json');
const CANLI_ADRES = 'https://mehmetkuru.dev/api/v1/modul-vitrini';
export const ZAMAN_ASIMI_MS = 20000;
export const YENIDEN_DENEME = 2;
const BEKLEMELER_MS = [1000, 3000];

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

/** Depodaki anlık görüntü (yoksa/bozuksa null). */
export function anlikFiyatlariOku() {
  try {
    const veri = JSON.parse(fs.readFileSync(ANLIK_YOLU, 'utf8'));
    if (fiyatlarGecerliMi(veri?.fiyatlar) && Object.keys(veri.fiyatlar).length > 0) return veri.fiyatlar;
  } catch (hata) {
    console.warn(`[moduller] Fiyat anlık görüntüsü okunamadı (${hata?.message ?? hata}).`);
  }
  return null;
}

const bekle = (ms) => new Promise((coz) => setTimeout(coz, ms));

async function canliOku(adres) {
  let sonHata = null;
  for (let deneme = 0; deneme <= YENIDEN_DENEME; deneme++) {
    if (deneme > 0) await bekle(BEKLEMELER_MS[deneme - 1] ?? 3000);
    const kesici = new AbortController();
    const zaman = setTimeout(() => kesici.abort(), ZAMAN_ASIMI_MS);
    try {
      const yanit = await fetch(adres, { headers: { accept: 'application/json' }, signal: kesici.signal });
      if (!yanit.ok) throw new Error(`HTTP ${yanit.status}`);
      const veri = await yanit.json();
      if (!fiyatlarGecerliMi(veri?.fiyatlar)) throw new Error('beklenmeyen biçim');
      if (Object.keys(veri.fiyatlar).length === 0) throw new Error('fiyat yok');
      return veri.fiyatlar;
    } catch (hata) {
      sonHata = hata;
      console.warn(`[moduller] Canlı fiyat denemesi ${deneme + 1}/${YENIDEN_DENEME + 1} düştü (${hata?.message ?? hata}).`);
    } finally {
      clearTimeout(zaman);
    }
  }
  throw sonHata ?? new Error('bilinmeyen hata');
}

let onbellek = null;

/** `{ fiyatlar, kaynak: 'canli' | 'anlik' | 'yok' }` */
export async function vitrinFiyatlariniYukle() {
  if (onbellek) return onbellek;
  const ayar = (process.env.MODUL_VITRINI_KAYNAGI || '').trim();
  if (ayar !== 'yok') {
    try {
      const fiyatlar = await canliOku(ayar || CANLI_ADRES);
      console.log(`[moduller] Fiyatlar canlı uçtan okundu: ${Object.keys(fiyatlar).length} ölçek.`);
      onbellek = { fiyatlar, kaynak: 'canli' };
      return onbellek;
    } catch {
      console.warn('[moduller] Canlı fiyatlar okunamadı — depodaki anlık görüntüye düşülüyor.');
    }
  }
  if ((process.env.MODUL_VITRINI_ANLIK || '').trim() !== 'yok') {
    const anlik = anlikFiyatlariOku();
    if (anlik) {
      console.log(`[moduller] Fiyatlar anlık görüntüden: ${Object.keys(anlik).length} ölçek.`);
      onbellek = { fiyatlar: anlik, kaynak: 'anlik' };
      return onbellek;
    }
  }
  console.warn('[moduller] Fiyat yok — vitrin fiyatsız üretilecek (JSON-LD offers yok).');
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
