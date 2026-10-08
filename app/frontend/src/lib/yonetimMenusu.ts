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
 * dokuz gruba ayrılıyor. Faz 11A: gruplar sol kenar çubuğunda akordeon
 * (`components/admin/YonetimKabugu.tsx`); en üstte grupsuz "Genel bakış".
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
    // Faz 5G: eski "İletişim formu" (`inquiries`) sekmesi kalktı — öğeleri Destek › Gelen kutusunda.
    // Faz 5K: ortaklık programı (ortaklar, başvurular, komisyonlar, ödeme talepleri, indirim kodları) — grubun sonunda.
    sekmeler: ['crm', 'siteAnalizleri', 'clients', 'teklifler', 'sozlesmeler', 'ortaklik'],
  },
  {
    anahtar: 'projeler',
    // Faz 6T: toplantılar (planlama, davet, tutanak, takvim aboneliği); Faz 6O: hedefler ve OKR (ajansın kendi OKR'ları).
    sekmeler: ['projects', 'zaman', 'projeSablonlari', 'dosyalar', 'toplantilar', 'hedefler'],
  },
  {
    anahtar: 'finans',
    sekmeler: ['invoices', 'odeme', 'abonelik', 'krediler', 'fiyatlandirmaV5', 'onMuhasebe'],
  },
  {
    anahtar: 'destek',
    sekmeler: ['gelenKutusu', 'tickets', 'mesajlar', 'siteler', 'bilgiBankasi', 'geriBildirim'],
  },
  {
    anahtar: 'araclar',
    sekmeler: ['aiAsistan', 'uzmanAsistanlar', 'randevu', 'qrMenu', 'etkinlik', 'egitim', 'sahaServisi', 'stokPos', 'ik', 'hukuk'],
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

/**
 * Faz 11A — grupların ÜSTÜNDE duran, hiçbir gruba girmeyen bölümler (kenar çubuğunun en
 * üstünde). Gruplu menünün sayımına (GRUPLAR, e2e `yonetimBolumSayisi`) girmez; `?sekme=`
 * ve hatırlanan sekme için yine geçerli ad.
 */
export const GENEL_BAKIS = 'genelBakis' as const;
export const UST_SEKMELER: readonly string[] = [GENEL_BAKIS];

/** Ad menü tanımındaki bir sekme mi (`?sekme=` ve hatırlanan sekme için). */
export function menudeVar(sekme: string | null | undefined): boolean {
  return !!sekme && (UST_SEKMELER.includes(sekme) || GRUPLAR.some((g) => g.sekmeler.includes(sekme)));
}

/** Faz 11A — kenar çubuğu daraltma tercihi (yalnız ikonlar); bu tarayıcıya özel kolaylık. */
const KENAR_DAR_ANAHTARI = 'mk_yonetim_kenar_dar';

export function kenarDarOku(): boolean {
  return yerelOku(KENAR_DAR_ANAHTARI) === '1';
}

export function kenarDarYaz(dar: boolean): void {
  yerelYaz(KENAR_DAR_ANAHTARI, dar ? '1' : '0');
}

/**
 * Kaldırılmış sekmelerin yeni yeri (eski `?sekme=` bağlantıları ve hatırlanan sekme için).
 * Faz 5G: "İletişim formu" → Gelen kutusu (iletişim formu süzgeciyle açılır).
 */
export const ESKI_SEKMELER: Readonly<Record<string, string>> = { inquiries: 'gelenKutusu' };

export function sekmeyiCoz(sekme: string | null | undefined): string | null {
  if (!sekme) return null;
  const yeni = ESKI_SEKMELER[sekme] ?? sekme;
  return menudeVar(yeni) ? yeni : null;
}
