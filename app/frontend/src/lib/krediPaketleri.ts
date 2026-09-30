/**
 * Kullandıkça Öde kredi paketleri — onaylı mockup'taki (v5) değerler birebir.
 * 1 Kredi = 1 Saat Senior, 12 ay geçerli. Tablo burada yalnız gösterim için;
 * satın alma tutarı sunucudaki aynı tablodan gelir
 * (`core/fiyat_hesaplama.py` → `KREDI_PAKETLERI`).
 *
 * Hem sitedeki Paketler bölümü hem müşteri panelindeki "Kredi al" aynı
 * tabloyu kullanıyor.
 */
export const KREDI_PAKETLERI: { kredi: number; bonus: number; fiyat: number; populer?: boolean }[] = [
  { kredi: 10, bonus: 0, fiyat: 1000 },
  { kredi: 25, bonus: 2, fiyat: 2250, populer: true },
  { kredi: 50, bonus: 5, fiyat: 4000 },
  { kredi: 100, bonus: 15, fiyat: 7000 },
];
