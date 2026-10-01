/**
 * Faz 4G — Pages Function'larının arka uca giden isteklerine "vekil imzası".
 *
 * Function'lar arka uca (Render) Worker alt isteğiyle gidiyor; o yüzden arka
 * uca varan `CF-Connecting-IP` ziyaretçinin değil Cloudflare'in adresi oluyor.
 * Ziyaretçinin adresi `X-MK-Istemci-IP` ile taşınıyor; arka uç bu başlığa
 * yalnız `X-MK-Vekil-Anahtari` ortak gizliyle (`VEKIL_ANAHTARI`, Pages ve
 * Render'da aynı değer) eşleşirse güveniyor (`app/backend/utils/istemci_ip.py`).
 *
 * Kurallar (dört Function da bu yardımcıyı kullanıyor):
 *   * Ziyaretçinin gönderdiği `X-MK-Vekil-Anahtari` ve `X-MK-Istemci-IP`
 *     HER ZAMAN siliniyor (uydurulmuş değer arka uca hiç ulaşmasın).
 *   * `X-MK-Istemci-IP` yalnız Cloudflare'in yazdığı `CF-Connecting-IP`'den.
 *   * `env.VEKIL_ANAHTARI` tanımlıysa `X-MK-Vekil-Anahtari` ekleniyor; değilse
 *     eklenmiyor ve istek yine çalışıyor (geçiş: arka uç anahtarsızken eski
 *     davranışı sürdürüyor).
 *
 * Yönlendirme notu: Pages Functions bir dosyayı ancak `onRequest*` dışa
 * aktarıyorsa rota yapıyor (workers-sdk `generateConfigFromFileTree`); bu
 * klasördeki yardımcılar o adları dışa aktarmadığı için rota değil, yalnız
 * içe aktarılıyor. `_` öneki bunu okuyana belli etmek için.
 */

export const VEKIL_BASLIGI = 'X-MK-Vekil-Anahtari';
export const IP_BASLIGI = 'X-MK-Istemci-IP';

/** Pages ortam değişkenindeki anahtar (boşluklar kırpılır; yoksa ''). */
export function vekilAnahtari(env) {
  const deger = env && typeof env.VEKIL_ANAHTARI === 'string' ? env.VEKIL_ANAHTARI.trim() : '';
  return deger;
}

/**
 * Arka uca gidecek başlıkları yerinde düzenler ve aynı nesneyi döndürür.
 * @param {Headers} basliklar  arka uç isteğinin başlıkları
 * @param {Request} istek      ziyaretçinin isteği
 * @param {object} env         Pages ortamı
 */
export function vekilBasliklari(basliklar, istek, env) {
  basliklar.delete(VEKIL_BASLIGI);
  basliklar.delete(IP_BASLIGI);
  const ip = istek && istek.headers ? istek.headers.get('CF-Connecting-IP') : null;
  if (ip) basliklar.set(IP_BASLIGI, ip);
  const anahtar = vekilAnahtari(env);
  if (anahtar) basliklar.set(VEKIL_BASLIGI, anahtar);
  return basliklar;
}
