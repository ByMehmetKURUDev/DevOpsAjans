/**
 * Gruplu panel menüsü — ortak mantık (Faz 7M).
 *
 * Yönetici paneli (Faz 7Y, `lib/yonetimMenusu.ts`) ve kalabalık müşteri paneli
 * (`lib/musteriMenusu.ts`) aynı düzeni kullanıyor: üstte gruplar, altta seçili
 * grubun bölümleri. Her panel yalnız kendi grup tanımını verir; yerleştirme ve
 * arama burada.
 *
 * Tanımda adı geçmeyen bir sekme kaybolmaz: sonda "diğer" grubunda görünür.
 */

export interface GrupTanimi<G extends string = string> {
  anahtar: G;
  /** Sekme anahtarları, menüde görünecekleri sırayla. */
  sekmeler: readonly string[];
}

export interface MenuSekmesi<K extends string = string> {
  key: K;
  label: string;
}

/** Hiçbir gruba yazılmamış sekmelerin toplandığı grup. */
export const DIGER = 'diger' as const;

export interface KurulmusGrup<S extends MenuSekmesi, G extends string = string> {
  anahtar: G | typeof DIGER;
  sekmeler: S[];
}

/**
 * Var olan sekmeleri gruplara yerleştirir. Tanımda olup panelde olmayan
 * sekmeler atlanır, boş gruplar çıkarılır; hiçbir gruba yazılmamış
 * sekmeler sonda "Diğer" grubunda toplanır.
 */
export function grupla<S extends MenuSekmesi, G extends string>(
  sekmeler: readonly S[],
  tanim: readonly GrupTanimi<G>[],
): KurulmusGrup<S, G>[] {
  const harita = new Map(sekmeler.map((s) => [s.key, s] as const));
  const kullanilan = new Set<string>();
  const sonuc: KurulmusGrup<S, G>[] = [];
  for (const g of tanim) {
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
  if (kalan.length) sonuc.push({ anahtar: DIGER, sekmeler: kalan });
  return sonuc;
}

/** Sekmenin bulunduğu grup (kurulmuş gruplar içinde). */
export function grubunuBul<S extends MenuSekmesi, G extends string>(
  gruplar: KurulmusGrup<S, G>[],
  sekme: string,
): G | typeof DIGER | null {
  return gruplar.find((g) => g.sekmeler.some((s) => s.key === sekme))?.anahtar ?? null;
}

/** Arama için harf/aksan farkını yok sayan sadeleştirme (İ/ı, ş, ç…). */
export function sadelestir(metin: string): string {
  return metin.toLocaleLowerCase('tr').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ı/g, 'i').trim();
}

/** Etiketi, anahtarı ya da grup adı aranan metni içeren sekmeler (grup sırasıyla). */
export function sekmeAra<S extends MenuSekmesi, G extends string>(
  gruplar: KurulmusGrup<S, G>[],
  aranan: string,
  grupAdi: (g: G | typeof DIGER) => string,
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

/** Tarayıcıya özel küçük kolaylık (son açılan sekme); okunamazsa yok sayılır. */
export function yerelOku(anahtar: string): string | null {
  try {
    return window.localStorage.getItem(anahtar);
  } catch {
    return null;
  }
}

export function yerelYaz(anahtar: string, deger: string): void {
  try {
    window.localStorage.setItem(anahtar, deger);
  } catch {
    /* gizli pencere / engellenmiş depolama: önemli değil */
  }
}
