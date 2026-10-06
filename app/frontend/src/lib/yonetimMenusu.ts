import {
  grupla,
  grubunuBul as ortakGrubunuBul,
  sekmeAra as ortakSekmeAra,
  yerelOku,
  yerelYaz,
  type KurulmusGrup as OrtakGrup,
  type MenuSekmesi,
} from '@/lib/grupluMenu';

/**
 * Yönetici paneli menüsü: 46 sekme tek satırda kalabalıktı. Sekmeler burada
 * dokuz gruba ayrılıyor; üst satırda gruplar, alt satırda seçili grubun
 * bölümleri görünüyor.
 *
 * Yeni bir sekme eklenip buraya yazılmazsa kaybolmaz: "Diğer" grubunda
 * görünür (bkz. `gruplariKur`). Böylece menü düzeni hiçbir sekmeyi gizlemez.
 */

export type GrupAnahtari =
  'site' | 'pazarlama' | 'satis' | 'projeler' | 'finans' | 'destek' | 'araclar' | 'otomasyon' | 'sistem' | 'diger';

export interface GrupTanimi {
  anahtar: GrupAnahtari;
  /** Sekme anahtarları, menüde görünecekleri sırayla. */
  sekmeler: readonly string[];
}

/** Grupların ve içlerindeki sekmelerin sırası (tek kaynak). */
export const GRUPLAR: readonly GrupTanimi[] = [
  {
    anahtar: 'site',
    sekmeler: ['analytics', 'settings', 'pages', 'blog', 'kaynaklar', 'marketplace'],
  },
  {
    anahtar: 'pazarlama',
    sekmeler: ['icerik', 'epostaPazarlama', 'dinamikQr', 'kartvizit'],
  },
  {
    anahtar: 'satis',
    sekmeler: ['crm', 'inquiries', 'siteAnalizleri', 'clients', 'teklifler', 'sozlesmeler'],
  },
  {
    anahtar: 'projeler',
    sekmeler: ['projects', 'zaman', 'projeSablonlari', 'dosyalar'],
  },
  {
    anahtar: 'finans',
    sekmeler: ['invoices', 'odeme', 'abonelik', 'krediler', 'fiyatlandirmaV5'],
  },
  {
    anahtar: 'destek',
    sekmeler: ['tickets', 'mesajlar', 'siteler', 'bilgiBankasi', 'geriBildirim'],
  },
  {
    anahtar: 'araclar',
    sekmeler: ['aiAsistan', 'uzmanAsistanlar', 'randevu', 'qrMenu', 'etkinlik', 'sahaServisi'],
  },
  {
    anahtar: 'otomasyon',
    sekmeler: ['otomasyon', 'baglantilar', 'api', 'islemler', 'notify'],
  },
  {
    anahtar: 'sistem',
    sekmeler: ['moduller', 'duyurular', 'guvenlik', 'denetim', 'copKutusu'],
  },
];

// Yerleştirme ve arama bütün paneller için ortak (Faz 7M: müşteri paneli de kullanıyor).
export { sadelestir, type MenuSekmesi } from '@/lib/grupluMenu';

export type KurulmusGrup<S extends MenuSekmesi> = OrtakGrup<S, GrupAnahtari>;

/**
 * Var olan sekmeleri gruplara yerleştirir. Tanımda olup panelde olmayan
 * sekmeler atlanır, boş gruplar çıkarılır; hiçbir gruba yazılmamış
 * sekmeler sonda "Diğer" grubunda toplanır.
 */
export function gruplariKur<S extends MenuSekmesi>(sekmeler: readonly S[]): KurulmusGrup<S>[] {
  return grupla(sekmeler, GRUPLAR);
}

/** Sekmenin bulunduğu grup (kurulmuş gruplar içinde). */
export function grubunuBul<S extends MenuSekmesi>(gruplar: KurulmusGrup<S>[], sekme: string): GrupAnahtari | null {
  return ortakGrubunuBul(gruplar, sekme);
}

/** Etiketi ya da anahtarı aranan metni içeren sekmeler (grup sırasıyla). */
export function sekmeAra<S extends MenuSekmesi>(
  gruplar: KurulmusGrup<S>[],
  aranan: string,
  grupAdi: (g: GrupAnahtari) => string,
): S[] {
  return ortakSekmeAra(gruplar, aranan, grupAdi);
}

/** Son açılan sekme (tarayıcıya özel kolaylık; okunamazsa yok sayılır). */
const SON_SEKME_ANAHTARI = 'mk_yonetim_son_sekme';

export function sonSekmeyiOku(): string | null {
  return yerelOku(SON_SEKME_ANAHTARI);
}

export function sonSekmeyiYaz(sekme: string): void {
  yerelYaz(SON_SEKME_ANAHTARI, sekme);
}

/** Ad menü tanımındaki bir sekme mi (`?sekme=` ve hatırlanan sekme için). */
export function menudeVar(sekme: string | null | undefined): boolean {
  return !!sekme && GRUPLAR.some((g) => g.sekmeler.includes(sekme));
}
