/**
 * Keşif Sihirbazı özetinin geçici saklanması.
 *
 * Sihirbaz özeti iletişim formuna sayfa durumuyla (`navigate` state)
 * taşıyor. Ama WhatsApp balonu `Layout` içinde, her sayfada duruyor ve o
 * duruma erişemiyor — sihirbazı doldurup WhatsApp'a basan ziyaretçi
 * anlattığı her şeyi baştan yazmak zorunda kalıyordu.
 *
 * `sessionStorage` seçildi çünkü bu bilgi sekme kapanınca gitmeli:
 * ortak bilgisayarda bir sonraki kişinin balonunda başkasının proje
 * özetini görmesi olmaz. Sunucuya da göndermiyoruz; ziyaretçi henüz
 * iletişime geçmeye karar vermemiş olabilir.
 *
 * Gizli sekmede erişim hata verebildiği için her çağrı sarmalanmış;
 * özet olmasa da site çalışmaya devam ediyor.
 */

const ANAHTAR = 'mk_kesif_ozeti';

export function kesifOzetiniSakla(ozet: string): void {
  try {
    sessionStorage.setItem(ANAHTAR, ozet);
  } catch {
    /* Depolama kapalıysa özet taşınmaz; akış yine çalışır. */
  }
}

export function kesifOzetiniOku(): string {
  try {
    return sessionStorage.getItem(ANAHTAR) || '';
  } catch {
    return '';
  }
}
