/**
 * Faz 7K — girişsiz sayfaların `fetch` yanıtları.
 *
 * Okunmayan yanıt gövdesi tarayıcıda isteği açık bırakıyor (DevTools'ta "bitmemiş" istek; bağlantı
 * havuzunda yer tutuyor). Gövdesi kullanılmayacak HER yanıt — 404/410 durum sayfaları, hata dalları,
 * yalnız durum koduna bakılan POST'lar, analitik işaretleri — buradan geçer. Gövde okunup atılır
 * (`body.cancel()` isteği "iptal edildi" olarak kapatıyor; okumak ise "bitti" yapıyor — yanıtlar küçük).
 */

/** Gövdeyi okuyup atar (zaten okunmuşsa bir şey yapmaz; ağ hatası yutulur). */
export async function govdeyiTuket(y: Response | null | undefined): Promise<void> {
  if (!y || y.bodyUsed) return;
  try {
    await y.arrayBuffer();
  } catch {
    /* bağlantı koptu ya da gövde kilitli: önemsiz */
  }
}

/** Başarılı yanıtta JSON (bozuksa `null`); başarısızda gövde tüketilip `null`. */
export async function jsonVeyaBos<T>(y: Response): Promise<T | null> {
  if (!y.ok) {
    await govdeyiTuket(y);
    return null;
  }
  return (await y.json().catch(() => null)) as T | null;
}
