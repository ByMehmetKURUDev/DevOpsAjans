import type { Birim, Satis, Urun } from '@/lib/stokPos';

/**
 * Faz 6Q — kasa ekranının çevrimdışı deposu (IndexedDB; açılamazsa bu sekmenin belleği).
 *
 * * `katalog`: son eşitlemedeki ürün kataloğu — ad, barkod/SKU, birim, satış fiyatı, KDV ve şube stoku.
 *   Maliyet (alış fiyatı) YAZILMAZ.
 * * `kuyruk`: bağlantı yokken kaydedilen satışlar ("ÇEVRİMDIŞI-n"). Gövde sunucuya gidecek satışın aynısı
 *   (`istemci_kimligi` = UUID → sunucuda tek kayıt); kişisel veri YOK: müşteri adı / alıcı çevrimdışı satışa
 *   eklenmez, kasiyer e-postası yerine `hesap|kişi` SHA-256 özeti tutulur (kuyruk yalnız aynı hesabın aynı
 *   kişisinin oturumuyla gönderilir). Hesap (e-posta) da depoda düz yazılmaz: anahtarlar `hesap` SHA-256 özeti.
 * * `sayac`: hesap başına "ÇEVRİMDIŞI-n" sayacı (bu cihazda artar).
 *
 * Sayfanın internetsiz SIFIRDAN açılması kapsam dışı: depo yalnız açık kasa sekmesinin bağlantısı koparsa
 * satışa devam etmek için. Her erişim hata yutar (depolama yoksa bellek; sayfa yenilenirse bellek gider).
 */

export interface KatalogUrunu {
  id: number;
  ad: string;
  barkod: string;
  sku: string | null;
  kategori: string | null;
  birim: Birim;
  satis_fiyati: number;
  kdv_orani: number;
  stok_takibi: boolean;
  kritik: boolean;
  stok: { toplam: number; konumlar: Record<string, number> };
}

export interface Katalog {
  /** Yazarken hesap e-postası verilir; depoda özetiyle saklanır. */
  hesap: string;
  /** ISO — son eşitleme. */
  zaman: string;
  urunler: KatalogUrunu[];
}

export type KuyrukDurumu = 'bekliyor' | 'hata';

export interface KuyrukKaydi {
  istemci_kimligi: string;
  /** `hesapOzeti(hesap)` — e-posta tutulmaz. */
  hesap: string;
  /** SHA-256(hesap|kişi) — e-posta tutulmaz. */
  kisi_ozeti: string;
  no: string;
  sira: number;
  /** ISO — cihazdaki satış anı. */
  zaman: string;
  toplam: number;
  govde: Record<string, unknown>;
  durum: KuyrukDurumu;
  hata?: { kod: string; durum: number; ek: Record<string, unknown> };
  deneme: number;
  /** Yeniden yazdırmak için cihazdaki fiş (kişisel veri yok). */
  fis: Satis;
}

const VT = 'mk_pos_cevrimdisi';
const SURUM = 1;
const ONEK = 'ÇEVRİMDIŞI';

export const cevrimdisiNo = (n: number) => `${ONEK}-${n}`;

// ---------------------------------------------------------------------------
// IndexedDB (söz tabanlı küçük sarmalayıcı) + bellek yedeği
// ---------------------------------------------------------------------------
let vtSozu: Promise<IDBDatabase | null> | null = null;
const bellek = { katalog: new Map<string, Katalog>(), kuyruk: new Map<string, KuyrukKaydi>(), sayac: new Map<string, number>() };

function vtAc(): Promise<IDBDatabase | null> {
  if (vtSozu) return vtSozu;
  vtSozu = new Promise((coz) => {
    try {
      if (typeof indexedDB === 'undefined') return coz(null);
      const istek = indexedDB.open(VT, SURUM);
      istek.onupgradeneeded = () => {
        const vt = istek.result;
        if (!vt.objectStoreNames.contains('katalog')) vt.createObjectStore('katalog', { keyPath: 'hesap' });
        if (!vt.objectStoreNames.contains('kuyruk')) vt.createObjectStore('kuyruk', { keyPath: 'istemci_kimligi' }).createIndex('hesap', 'hesap');
        if (!vt.objectStoreNames.contains('sayac')) vt.createObjectStore('sayac', { keyPath: 'hesap' });
      };
      istek.onsuccess = () => coz(istek.result);
      istek.onerror = () => coz(null);
      istek.onblocked = () => coz(null);
    } catch {
      coz(null);
    }
  });
  return vtSozu;
}

/** IndexedDB kullanılabiliyor mu (değilse kuyruk yalnız bu sekmenin belleğinde — yenilenirse kaybolur). */
export async function kalici(): Promise<boolean> {
  return (await vtAc()) !== null;
}

function islem<T>(vt: IDBDatabase, depo: string, kip: IDBTransactionMode, is: (d: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  return new Promise((coz, red) => {
    try {
      const tx = vt.transaction(depo, kip);
      const istek = is(tx.objectStore(depo));
      tx.oncomplete = () => coz(istek ? (istek.result as T) : undefined);
      tx.onerror = () => red(tx.error);
      tx.onabort = () => red(tx.error);
    } catch (e) {
      red(e);
    }
  });
}

// ---------------------------------------------------------------------------
// Özetler (e-posta depoya düz yazılmaz)
// ---------------------------------------------------------------------------
async function ozet(metin: string): Promise<string> {
  try {
    if (typeof crypto !== 'undefined' && crypto.subtle) {
      const o = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(metin));
      return Array.from(new Uint8Array(o), (b) => b.toString(16).padStart(2, '0')).join('').slice(0, 32);
    }
  } catch {
    /* güvenli bağlam yok */
  }
  // FNV-1a (yedek; amaç e-postayı düz yazmamak).
  let h = 0x811c9dc5;
  for (let i = 0; i < metin.length; i++) {
    h ^= metin.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `fnv-${h.toString(16)}`;
}

const kucukHarf = (s: string) => s.trim().toLowerCase();

/** Depo anahtarı: hesabın özeti. */
export const hesapOzeti = (hesap: string) => ozet(`hesap|${kucukHarf(hesap)}`);

/** Kuyruğu gönderebilecek kişinin özeti (aynı hesap + aynı kişi). */
export const kisiOzeti = (hesap: string, kisi: string) => ozet(`${kucukHarf(hesap)}|${kucukHarf(kisi)}`);

// ---------------------------------------------------------------------------
// Katalog
// ---------------------------------------------------------------------------
export function katalogUrunu(u: Urun): KatalogUrunu {
  // Bilerek seçili alanlar: maliyet (alis_fiyati), notlar, varyant bilgisi cihaza yazılmaz.
  return {
    id: u.id,
    ad: u.ad,
    barkod: u.barkod,
    sku: u.sku,
    kategori: u.kategori,
    birim: u.birim,
    satis_fiyati: u.satis_fiyati,
    kdv_orani: u.kdv_orani,
    stok_takibi: u.stok_takibi,
    kritik: u.kritik,
    stok: { toplam: u.stok.toplam, konumlar: { ...u.stok.konumlar } },
  };
}

/** Hesabın son eşitlenen kataloğu; dönen kayıtta `hesap` yine hesap e-postasıdır (depoda özet). */
export async function katalogOku(hesap: string): Promise<Katalog | null> {
  const anahtar = await hesapOzeti(hesap);
  const vt = await vtAc();
  let kayit: Katalog | null = null;
  if (vt) {
    try {
      kayit = ((await islem<Katalog>(vt, 'katalog', 'readonly', (d) => d.get(anahtar))) as Katalog | undefined) || null;
    } catch {
      kayit = null;
    }
  }
  kayit = kayit || bellek.katalog.get(anahtar) || null;
  return kayit ? { ...kayit, hesap } : null;
}

/** `k.hesap` hesap e-postası; depoya özetiyle yazılır. */
export async function katalogYaz(k: Katalog): Promise<void> {
  const kayit = { ...k, hesap: await hesapOzeti(k.hesap) };
  bellek.katalog.set(kayit.hesap, kayit);
  const vt = await vtAc();
  if (!vt) return;
  try {
    await islem(vt, 'katalog', 'readwrite', (d) => d.put(kayit));
  } catch {
    /* kota/özel kip: bellekte kalır */
  }
}

// ---------------------------------------------------------------------------
// Kuyruk
// ---------------------------------------------------------------------------
/** Hesabın kuyruğu (hesap e-postasıyla çağrılır; kayıtlar özetle eşlenir). */
export async function kuyrukListe(hesap: string): Promise<KuyrukKaydi[]> {
  const anahtar = await hesapOzeti(hesap);
  const vt = await vtAc();
  let liste: KuyrukKaydi[] = [];
  if (vt) {
    try {
      liste = ((await islem<KuyrukKaydi[]>(vt, 'kuyruk', 'readonly', (d) => d.index('hesap').getAll(anahtar))) as KuyrukKaydi[] | undefined) || [];
    } catch {
      liste = [];
    }
  }
  // Bellekte kalmış (IndexedDB yazılamamış) kayıtlar da sayılır.
  for (const k of bellek.kuyruk.values()) if (k.hesap === anahtar && !liste.some((x) => x.istemci_kimligi === k.istemci_kimligi)) liste.push(k);
  return liste.sort((a, b) => a.sira - b.sira || a.zaman.localeCompare(b.zaman));
}

export async function kuyrugaYaz(k: KuyrukKaydi): Promise<void> {
  const vt = await vtAc();
  if (vt) {
    try {
      await islem(vt, 'kuyruk', 'readwrite', (d) => d.put(k));
      bellek.kuyruk.delete(k.istemci_kimligi);
      return;
    } catch {
      /* belleğe düş */
    }
  }
  bellek.kuyruk.set(k.istemci_kimligi, k);
}

export async function kuyruktanSil(istemciKimligi: string): Promise<void> {
  bellek.kuyruk.delete(istemciKimligi);
  const vt = await vtAc();
  if (!vt) return;
  try {
    await islem(vt, 'kuyruk', 'readwrite', (d) => d.delete(istemciKimligi));
  } catch {
    /* yok say */
  }
}

/** Hesap başına artan çevrimdışı fiş sayacı (1, 2, 3 …). */
export async function sonrakiSira(hesapEposta: string): Promise<number> {
  const hesap = await hesapOzeti(hesapEposta);
  const vt = await vtAc();
  if (vt) {
    try {
      return await new Promise<number>((coz, red) => {
        const tx = vt.transaction('sayac', 'readwrite');
        const d = tx.objectStore('sayac');
        let n = 1;
        const oku = d.get(hesap);
        oku.onsuccess = () => {
          n = Number((oku.result as { n?: number } | undefined)?.n || 0) + 1;
          d.put({ hesap, n });
        };
        tx.oncomplete = () => coz(n);
        tx.onerror = () => red(tx.error);
        tx.onabort = () => red(tx.error);
      });
    } catch {
      /* belleğe düş */
    }
  }
  const n = (bellek.sayac.get(hesap) || 0) + 1;
  bellek.sayac.set(hesap, n);
  return n;
}

// ---------------------------------------------------------------------------
// Yerel arama
// ---------------------------------------------------------------------------
const kucuk = (s: string) => s.toLocaleLowerCase('tr');

/** Barkod / SKU birebir. */
export function koddanBul(urunler: KatalogUrunu[], kod: string): KatalogUrunu | null {
  // Okuyucunun eklediği boşluk / denetim karakterleri atılır (sunucudaki `okutma_kodu` gibi).
  const k = Array.from(kod)
    .filter((c) => c.charCodeAt(0) > 32)
    .join('');
  if (!k) return null;
  return urunler.find((u) => u.barkod === k || (!!u.sku && u.sku === k)) || null;
}

/** Ad (büyük/küçük harf duyarsız, Türkçe), barkod/SKU başı. */
export function yerelAra(urunler: KatalogUrunu[], ara: string, adet = 30): KatalogUrunu[] {
  const a = ara.trim();
  if (!a) return urunler.slice(0, adet);
  const ak = kucuk(a);
  return urunler.filter((u) => kucuk(u.ad).includes(ak) || u.barkod.startsWith(a) || (!!u.sku && u.sku.startsWith(a))).slice(0, adet);
}

/** Satılan miktarları (binde değil, birim) yerel stoktan düşer — gösterim için; asıl stok sunucuda. */
export function stokDus<T extends { id: number; stok_takibi: boolean; stok: { toplam: number; konumlar: Record<string, number> } }>(
  urunler: T[],
  satilan: { urun_id: number; adet: number }[],
  konumId: number
): T[] {
  const harita = new Map<number, number>();
  for (const s of satilan) harita.set(s.urun_id, (harita.get(s.urun_id) || 0) + s.adet);
  return urunler.map((u) => {
    const d = harita.get(u.id);
    if (!d || !u.stok_takibi) return u;
    const anahtar = String(konumId);
    const yuvar = (n: number) => Math.round(n * 1000) / 1000;
    return { ...u, stok: { toplam: yuvar(u.stok.toplam - d), konumlar: { ...u.stok.konumlar, [anahtar]: yuvar((u.stok.konumlar[anahtar] ?? 0) - d) } } };
  });
}
