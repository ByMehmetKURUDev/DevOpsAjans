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

export interface MenuSekmesi<K extends string = string> {
  key: K;
  label: string;
}

export interface KurulmusGrup<S extends MenuSekmesi> {
  anahtar: GrupAnahtari;
  sekmeler: S[];
}

/**
 * Var olan sekmeleri gruplara yerleştirir. Tanımda olup panelde olmayan
 * sekmeler atlanır, boş gruplar çıkarılır; hiçbir gruba yazılmamış
 * sekmeler sonda "Diğer" grubunda toplanır.
 */
export function gruplariKur<S extends MenuSekmesi>(sekmeler: readonly S[]): KurulmusGrup<S>[] {
  const harita = new Map(sekmeler.map((s) => [s.key, s] as const));
  const kullanilan = new Set<string>();
  const sonuc: KurulmusGrup<S>[] = [];
  for (const g of GRUPLAR) {
    const icindekiler: S[] = [];
    for (const k of g.sekmeler) {
      const s = harita.get(k);
      if (s && !kullanilan.has(k)) {
        icindekiler.push(s);
        kullanilan.add(k);
      }
    }
    if (icindekiler.length) sonuc.push({ anahtar: g.anahtar, sekmeler: icindekiler });
  }
  const kalan = sekmeler.filter((s) => !kullanilan.has(s.key));
  if (kalan.length) sonuc.push({ anahtar: 'diger', sekmeler: kalan });
  return sonuc;
}

/** Sekmenin bulunduğu grup (kurulmuş gruplar içinde). */
export function grubunuBul<S extends MenuSekmesi>(gruplar: KurulmusGrup<S>[], sekme: string): GrupAnahtari | null {
  return gruplar.find((g) => g.sekmeler.some((s) => s.key === sekme))?.anahtar ?? null;
}

/** Arama için harf/aksan farkını yok sayan sadeleştirme (İ/ı, ş, ç…). */
export function sadelestir(metin: string): string {
  return metin.toLocaleLowerCase('tr').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ı/g, 'i').trim();
}

/** Etiketi ya da anahtarı aranan metni içeren sekmeler (grup sırasıyla). */
export function sekmeAra<S extends MenuSekmesi>(
  gruplar: KurulmusGrup<S>[],
  aranan: string,
  grupAdi: (g: GrupAnahtari) => string,
): S[] {
  const q = sadelestir(aranan);
  if (!q) return [];
  const bulunan: S[] = [];
  for (const g of gruplar) {
    const grupEslesti = sadelestir(grupAdi(g.anahtar)).includes(q);
    for (const s of g.sekmeler) {
      if (grupEslesti || sadelestir(s.label).includes(q) || sadelestir(s.key).includes(q)) bulunan.push(s);
    }
  }
  return bulunan;
}

/** Son açılan sekme (tarayıcıya özel kolaylık; okunamazsa yok sayılır). */
const SON_SEKME_ANAHTARI = 'mk_yonetim_son_sekme';

export function sonSekmeyiOku(): string | null {
  try {
    return window.localStorage.getItem(SON_SEKME_ANAHTARI);
  } catch {
    return null;
  }
}

export function sonSekmeyiYaz(sekme: string): void {
  try {
    window.localStorage.setItem(SON_SEKME_ANAHTARI, sekme);
  } catch {
    /* gizli pencere / engellenmiş depolama: önemli değil */
  }
}

/** Ad menü tanımındaki bir sekme mi (`?sekme=` ve hatırlanan sekme için). */
export function menudeVar(sekme: string | null | undefined): boolean {
  return !!sekme && GRUPLAR.some((g) => g.sekmeler.includes(sekme));
}
