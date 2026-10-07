/**
 * Faz 4M — QR menü ve WhatsApp katalog: panel ile herkese açık sayfanın ORTAK
 * türleri ve küçük yardımcıları. Ağır bağımlılık yok (SDK, ikon, UI): herkese
 * açık `/menu/<slug>` parçası küçük kalsın.
 *
 * Fiyatlar sunucudan 2 haneli sayı olarak geliyor; asıl hesap (sepet, kupon,
 * sipariş) SUNUCUDA. İstemcideki toplam yalnız gösterim için ve sunucunun
 * `/hesapla` yanıtıyla değişiyor.
 */

export const DILLER = ['tr', 'en', 'de', 'ru', 'zh', 'hi', 'ar'] as const;
export type MenuDili = (typeof DILLER)[number];
export const DIL_ADLARI: Record<MenuDili, string> = {
  tr: 'Türkçe',
  en: 'English',
  de: 'Deutsch',
  ru: 'Русский',
  zh: '中文',
  hi: 'हिन्दी',
  ar: 'العربية',
};
export const ALERJENLER = [
  'gluten',
  'kabuklular',
  'yumurta',
  'balik',
  'yer_fistigi',
  'soya',
  'sut',
  'sert_kabuklu',
  'kereviz',
  'hardal',
  'susam',
  'sulfit',
  'aci_bakla',
  'yumusakcalar',
] as const;
export type Alerjen = (typeof ALERJENLER)[number];
export const ETIKETLER = ['vegan', 'vejetaryen', 'glutensiz', 'acili', 'yeni', 'cok_satan'] as const;
export type Etiket = (typeof ETIKETLER)[number];
export const TESLIMATLAR = ['gel_al', 'paket', 'masada'] as const;
export type Teslimat = (typeof TESLIMATLAR)[number];
export type Duzen = 'menu' | 'katalog';

/** Etiket rozetinin rengi (Tailwind sınıfları). */
export const ETIKET_RENGI: Record<Etiket, string> = {
  vegan: 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200',
  vejetaryen: 'border-lime-400/40 bg-lime-500/15 text-lime-200',
  glutensiz: 'border-amber-400/40 bg-amber-500/15 text-amber-100',
  acili: 'border-red-400/40 bg-red-500/15 text-red-200',
  yeni: 'border-sky-400/40 bg-sky-500/15 text-sky-200',
  cok_satan: 'border-fuchsia-400/40 bg-fuchsia-500/15 text-fuchsia-200',
};

export type Ceviriler = Partial<Record<MenuDili, { ad?: string; aciklama?: string }>>;
export type TekCeviri = Partial<Record<MenuDili, string>>;

export interface MenuGorsel {
  anahtar: string;
  k: string;
  b: string;
  genislik: number | null;
  yukseklik: number | null;
}

export interface Secenek {
  id: string;
  ad: string;
  fiyat_farki: number;
  ceviriler?: TekCeviri;
}

export interface SecenekGrubu {
  id: string;
  ad: string;
  tur: 'tek' | 'coklu';
  zorunlu: boolean;
  en_az: number;
  en_cok: number;
  secenekler: Secenek[];
  ceviriler?: TekCeviri;
}

export interface MenuKategori {
  id: number;
  ad: string;
  ceviriler: Ceviriler;
  gorsel: MenuGorsel | null;
  sira?: number;
  gizli?: boolean;
}

export interface MenuUrun {
  id: number;
  kategori_id: number;
  ad: string;
  aciklama: string;
  fiyat: number;
  indirimli_fiyat: number | null;
  gorsel: MenuGorsel | null;
  secenek_gruplari: SecenekGrubu[];
  etiketler: Etiket[];
  alerjenler: Alerjen[];
  kalori: number | null;
  stokta_yok: boolean;
  gizli?: boolean;
  sira?: number;
  ceviriler: Ceviriler;
}

export interface SiparisAyarlari {
  whatsapp_acik: boolean;
  gel_al: boolean;
  paket: boolean;
  masada: boolean;
  en_dusuk_tutar: number;
  paket_ucreti: number;
  siparis_notu: string;
  kapaliyken_siparis: boolean;
}

export type CalismaSaatleri = Partial<Record<'0' | '1' | '2' | '3' | '4' | '5' | '6', [string, string][]>>;

/** `GET /api/v1/menu/<slug>` yanıtı. */
export interface AcikMenu {
  slug: string;
  duzen: Duzen;
  ad: string;
  aciklama: string;
  ceviriler: Ceviriler;
  logo: MenuGorsel | null;
  kapak: MenuGorsel | null;
  tema_rengi: string;
  adres: string;
  telefon: string;
  para_birimi: string;
  varsayilan_dil: MenuDili;
  diller: MenuDili[];
  acik: boolean | null;
  calisma_saatleri: CalismaSaatleri;
  saat_dilimi: string;
  siparis: SiparisAyarlari;
  kupon_var: boolean;
  saklama_gun: number;
  indekslenebilir: boolean;
  kategoriler: MenuKategori[];
  urunler: MenuUrun[];
  /** Faz 4L: hesabın marka teması (mağazanın kendi tema rengi seçiliyse `sayfa_ozel`). */
  marka?: import('@/lib/marka').AcikMarka;
}

/** Sunucunun hesapladığı sepet (`/hesapla`). */
export interface SepetHesabi {
  kalemler: {
    urun_id: number;
    ad: string;
    ad_dil: string;
    adet: number;
    birim_fiyat: number;
    tutar: number;
    secimler: Record<string, string[]>;
    secenekler: { grup: string; ad: string; ad_dil: string; fiyat_farki: number }[];
  }[];
  ara_toplam: number;
  indirim: number;
  kupon: { kod: string; gecerli: boolean; hata: string | null; tur: string | null; deger: number | null } | null;
  paket_ucreti: number;
  toplam: number;
  en_dusuk_tutar: number;
  en_dusuk_eksik: number;
  teslimat: Teslimat;
}

/** Kaydın etkin dildeki adı/açıklaması (çeviri yoksa varsayılan dildeki metin). */
export function yerel(metin: string, ceviriler: Ceviriler | undefined, dil: string, alan: 'ad' | 'aciklama' = 'ad'): string {
  const c = ceviriler?.[dil as MenuDili];
  return (c && c[alan]) || metin;
}

export function tekYerel(metin: string, ceviriler: TekCeviri | undefined, dil: string): string {
  return ceviriler?.[dil as MenuDili] || metin;
}

/** Para birimini dile göre biçimler (`Intl.NumberFormat`); geçersiz para kodunda sade sayı. */
export function paraYaz(tutar: number, para: string, dil: string): string {
  const yerelAd = dil === 'ar' ? 'ar-u-nu-latn' : dil;
  try {
    // "TRY 50.00" yerine "₺50.00": dar sembol her dilde para birimi işaretini gösterir.
    return new Intl.NumberFormat(yerelAd, { style: 'currency', currency: para, currencyDisplay: 'narrowSymbol' }).format(tutar);
  } catch {
    try {
      return new Intl.NumberFormat(yerelAd, { style: 'currency', currency: para }).format(tutar);
    } catch {
      return `${tutar.toFixed(2)} ${para}`;
    }
  }
}

/** Ürünün geçerli birim fiyatı (indirimli varsa o). */
export function birimFiyat(u: Pick<MenuUrun, 'fiyat' | 'indirimli_fiyat'>): number {
  return u.indirimli_fiyat !== null && u.indirimli_fiyat >= 0 && u.indirimli_fiyat < u.fiyat ? u.indirimli_fiyat : u.fiyat;
}

/** Seçimlerin fiyat farkı (yalnız gösterim). */
export function secimFarki(u: MenuUrun, secimler: Record<string, string[]>): number {
  let fark = 0;
  for (const g of u.secenek_gruplari) {
    for (const sid of secimler[g.id] || []) {
      const s = g.secenekler.find((x) => x.id === sid);
      if (s) fark += s.fiyat_farki;
    }
  }
  return fark;
}

/** Seçimler grup kurallarına uyuyor mu? Uymayan ilk grubun kimliği ya da null. */
export function eksikGrup(u: MenuUrun, secimler: Record<string, string[]>): string | null {
  for (const g of u.secenek_gruplari) {
    const n = (secimler[g.id] || []).length;
    if (n < g.en_az || n > g.en_cok) return g.id;
  }
  return null;
}

/** Varsayılan seçimler: zorunlu tek seçimli grupta ilk seçenek. */
export function varsayilanSecimler(u: MenuUrun): Record<string, string[]> {
  const s: Record<string, string[]> = {};
  for (const g of u.secenek_gruplari) {
    if (g.tur === 'tek' && g.zorunlu && g.secenekler[0]) s[g.id] = [g.secenekler[0].id];
  }
  return s;
}

/** Görsel `srcset`'i (küçük 480 px, büyük 1200 px). */
export function srcset(g: MenuGorsel): string {
  return `${g.k} 480w, ${g.b} 1200w`;
}

/** Görselin en-boy oranından küçük boyun yüksekliği (CLS olmasın). */
export function kucukBoyut(g: MenuGorsel): { width: number; height: number } {
  const w = g.genislik || 480;
  const h = g.yukseklik || 360;
  const oran = Math.min(1, 480 / Math.max(w, h));
  return { width: Math.round(w * oran), height: Math.round(h * oran) };
}

export const GUNLER = ['0', '1', '2', '3', '4', '5', '6'] as const;
