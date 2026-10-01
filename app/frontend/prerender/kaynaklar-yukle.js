/**
 * Kaynaklar — derleme verisini yükler (yalnız Node: vite.config ve betikler).
 *
 * Sıra:
 *   1. Canlı API: `https://mehmetkuru.dev/api/v1/kaynaklar?bicim=tam`
 *      (5 sn zaman aşımı). Panelde eklenen/düzenlenen kaynaklar böylece
 *      bir sonraki yayında prerender HTML'ine ve site haritasına giriyor.
 *   2. Erişilemezse (uyuyan sunucu, ağ yok, eski sürüm 404): depodaki tohum
 *      dosyası `app/backend/data/kaynaklar_tohum.json`.
 *   3. O da okunamazsa boş veri — derleme hiçbir koşulda düşmez; Kaynaklar
 *      liste sayfası yine üretilir, ayrıntı sayfası üretilmez.
 *
 * `KAYNAKLAR_KAYNAGI=yok` canlı isteği atlar (yerel/çevrimdışı derleme);
 * başka bir değer canlı adresin yerine geçer.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const kok = path.dirname(fileURLToPath(import.meta.url));
export const TOHUM_YOLU = path.resolve(kok, '../../backend/data/kaynaklar_tohum.json');
const CANLI_ADRES = 'https://mehmetkuru.dev/api/v1/kaynaklar?bicim=tam';
const ZAMAN_ASIMI_MS = 5000;

function gecerliMi(veri) {
  return Boolean(veri) && Array.isArray(veri.kaynaklar) && Array.isArray(veri.kategoriler);
}

async function canlidanOku(adres) {
  const kesici = new AbortController();
  const zaman = setTimeout(() => kesici.abort(), ZAMAN_ASIMI_MS);
  try {
    const yanit = await fetch(adres, { headers: { accept: 'application/json' }, signal: kesici.signal });
    if (!yanit.ok) throw new Error(`HTTP ${yanit.status}`);
    const veri = await yanit.json();
    if (!gecerliMi(veri)) throw new Error('beklenmeyen biçim');
    return veri;
  } finally {
    clearTimeout(zaman);
  }
}

function tohumdanOku() {
  const veri = JSON.parse(fs.readFileSync(TOHUM_YOLU, 'utf8'));
  if (!gecerliMi(veri)) throw new Error('tohum dosyası beklenen biçimde değil');
  return veri;
}

let onbellek = null;

/** `{ kategoriler, kaynaklar, kaynak: 'canli' | 'tohum' | 'bos' }` */
export async function kaynakVerisiniYukle() {
  if (onbellek) return onbellek;
  const ayar = (process.env.KAYNAKLAR_KAYNAGI || '').trim();
  if (ayar !== 'yok') {
    const adres = ayar || CANLI_ADRES;
    try {
      const veri = await canlidanOku(adres);
      console.log(`[kaynaklar] Canlı API'den okundu: ${veri.kaynaklar.length} kaynak.`);
      onbellek = { ...veri, kaynak: 'canli' };
      return onbellek;
    } catch (hata) {
      console.warn(`[kaynaklar] Canlı API okunamadı (${hata?.message ?? hata}) — tohum dosyası kullanılıyor.`);
    }
  }
  try {
    const veri = tohumdanOku();
    console.log(`[kaynaklar] Tohum dosyasından okundu: ${veri.kaynaklar.length} kaynak.`);
    onbellek = { ...veri, kaynak: 'tohum' };
  } catch (hata) {
    console.warn(`[kaynaklar] Tohum dosyası okunamadı (${hata?.message ?? hata}) — kaynak sayfaları boş üretilecek.`);
    onbellek = { kategoriler: [], kaynaklar: [], kaynak: 'bos' };
  }
  return onbellek;
}

const SANAL_KIMLIK = 'virtual:kaynaklar-veri';
const COZULMUS_KIMLIK = '\0virtual:kaynaklar-veri';

/**
 * Vite eklentisi: derleme verisini `virtual:kaynaklar-veri` modülü olarak
 * yalnız prerender betiğine (prerender/app.js) verir. İstemci kodu bu
 * modülü içe aktarmıyor — veri ana pakete ya da sayfa paketine girmiyor.
 */
export function kaynakVeriEklentisi(veri) {
  return {
    name: 'mk-kaynaklar-veri',
    resolveId(kimlik) {
      return kimlik === SANAL_KIMLIK ? COZULMUS_KIMLIK : null;
    },
    load(kimlik) {
      if (kimlik !== COZULMUS_KIMLIK) return null;
      const temiz = { kategoriler: veri?.kategoriler ?? [], kaynaklar: veri?.kaynaklar ?? [] };
      return `export default ${JSON.stringify(temiz)};`;
    },
  };
}
