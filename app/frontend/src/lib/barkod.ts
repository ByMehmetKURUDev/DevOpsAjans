/**
 * Faz 6P — saf TypeScript barkod çizimi (paket yok): EAN-13, EAN-8 ve Code128-B → SVG yol verisi.
 *
 * Çıktı modül (çizgi birimi) dizisidir; `svgYolu` siyah çubukları tek bir `<path>` olarak verir. Etiket
 * ve okutma testleri için sunucudaki kontrol hanesi hesabıyla (services/stok_pos.ean_kontrol_hanesi) aynı.
 */

const L = ['0001101', '0011001', '0010011', '0111101', '0100011', '0110001', '0101111', '0111011', '0110111', '0001011'];
const G = ['0100111', '0110011', '0011011', '0100001', '0011101', '0111001', '0000101', '0010001', '0001001', '0010111'];
const R = ['1110010', '1100110', '1101100', '1000010', '1011100', '1001110', '1010000', '1000100', '1001000', '1110100'];
/** EAN-13 ilk hanesine göre sol yarının L/G düzeni. */
const PARITE = ['LLLLLL', 'LLGLGG', 'LLGGLG', 'LLGGGL', 'LGLLGG', 'LGGLLG', 'LGGGLL', 'LGLGLG', 'LGLGGL', 'LGGLGL'];

/** Code 128 desenleri (çubuk/boşluk genişlikleri; 0–105, 106 = dur). */
const C128 = [
  '212222', '222122', '222221', '121223', '121322', '131222', '122213', '122312', '132212', '221213',
  '221312', '231212', '112232', '122132', '122231', '113222', '123122', '123221', '223211', '221132',
  '221231', '213212', '223112', '312131', '311222', '321122', '321221', '312212', '322112', '322211',
  '212123', '212321', '232121', '111323', '131123', '131321', '112313', '132113', '132311', '211313',
  '231113', '231311', '112133', '112331', '132131', '113123', '113321', '133121', '313121', '211331',
  '231131', '213113', '213311', '213131', '311123', '311321', '331121', '312113', '312311', '332111',
  '314111', '221411', '431111', '111224', '111422', '121124', '121421', '141122', '141221', '112214',
  '112412', '122114', '122411', '142112', '142211', '241211', '221114', '413111', '241112', '134111',
  '111242', '121142', '121241', '114212', '124112', '124211', '411212', '421112', '421211', '212141',
  '214121', '412121', '111143', '111341', '131141', '114113', '114311', '411113', '411311', '113141',
  '114131', '311141', '411131', '211412', '211214', '211232', '2331112',
];

export type BarkodTuru = 'ean13' | 'ean8' | 'code128';

export function eanKontrolHanesi(govde: string): number {
  let toplam = 0;
  for (let i = 0; i < govde.length; i++) {
    const rakam = Number(govde[govde.length - 1 - i]);
    toplam += rakam * (i % 2 === 0 ? 3 : 1);
  }
  return (10 - (toplam % 10)) % 10;
}

export function eanGecerliMi(kod: string): boolean {
  return /^\d{8}$|^\d{12,14}$/.test(kod) && eanKontrolHanesi(kod.slice(0, -1)) === Number(kod[kod.length - 1]);
}

export function barkodTuru(kod: string): BarkodTuru {
  if (/^\d{13}$/.test(kod) && eanGecerliMi(kod)) return 'ean13';
  if (/^\d{8}$/.test(kod) && eanGecerliMi(kod)) return 'ean8';
  return 'code128';
}

function ean13Modulleri(kod: string): string {
  const parite = PARITE[Number(kod[0])];
  let m = '101';
  for (let i = 1; i <= 6; i++) m += (parite[i - 1] === 'L' ? L : G)[Number(kod[i])];
  m += '01010';
  for (let i = 7; i <= 12; i++) m += R[Number(kod[i])];
  return m + '101';
}

function ean8Modulleri(kod: string): string {
  let m = '101';
  for (let i = 0; i < 4; i++) m += L[Number(kod[i])];
  m += '01010';
  for (let i = 4; i < 8; i++) m += R[Number(kod[i])];
  return m + '101';
}

function code128Modulleri(metin: string): string {
  const degerler = [104];
  for (const ch of metin) {
    const k = ch.charCodeAt(0);
    degerler.push(k >= 32 && k <= 126 ? k - 32 : 31); // yazdırılamayan → "?"
  }
  let toplam = degerler[0];
  for (let i = 1; i < degerler.length; i++) toplam += i * degerler[i];
  degerler.push(toplam % 103, 106);
  let m = '';
  for (const d of degerler) {
    const desen = C128[d];
    for (let i = 0; i < desen.length; i++) m += (i % 2 === 0 ? '1' : '0').repeat(Number(desen[i]));
  }
  return m;
}

export interface Cizim {
  tur: BarkodTuru;
  /** '1' çubuk, '0' boşluk; sessiz bölge dahil. */
  moduller: string;
}

export function barkodCiz(kod: string): Cizim {
  const tur = barkodTuru(kod);
  const govde = tur === 'ean13' ? ean13Modulleri(kod) : tur === 'ean8' ? ean8Modulleri(kod) : code128Modulleri(kod);
  const sessiz = tur === 'code128' ? 10 : tur === 'ean13' ? 9 : 7;
  return { tur, moduller: '0'.repeat(sessiz) + govde + '0'.repeat(sessiz) };
}

/** Siyah çubukları tek bir SVG yolu olarak verir (genişlik = modül sayısı, yükseklik = `yukseklik`). */
export function svgYolu(moduller: string, yukseklik = 50): string {
  let d = '';
  let i = 0;
  while (i < moduller.length) {
    if (moduller[i] !== '1') {
      i++;
      continue;
    }
    let j = i;
    while (j < moduller.length && moduller[j] === '1') j++;
    d += `M${i} 0h${j - i}v${yukseklik}h-${j - i}z`;
    i = j;
  }
  return d;
}
