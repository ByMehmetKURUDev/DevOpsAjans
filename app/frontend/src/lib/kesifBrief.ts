import { client } from '@/lib/sdkClient';

/**
 * Keşif cevaplarından uzman promptları.
 *
 * Arka uç metinleri sabit şablondan üretiyor; dil modeline sormuyor.
 * Böylece her seferinde aynı çıktı geliyor, anahtar gerekmiyor ve modelin
 * uyduracağı teknik detay riski kalmıyor.
 *
 * Uç yalnızca yöneticiye açık — üretilen metin müşteriye gösterilecek bir
 * şey değil, iç çalışma metni.
 */

export interface BriefGirdisi {
  amac: string;
  serbest: string;
  kapsam: string[];
  zaman: string;
  butce: string;
  musteri?: string;
  proje?: string;
  ozet?: string;
}

export interface RolPromptu {
  id: string;
  ad: string;
  prompt: string;
}

export interface Brief {
  baslik: string;
  kunye: string;
  roller: RolPromptu[];
  zincir: string;
}

/** Sihirbazdaki anahtarlar — arka uçtaki sözlüklerle aynı olmak zorunda. */
export const AMAC_SECENEKLERI = [
  'website',
  'eticaret',
  'saas',
  'mobil',
  'mevcut',
] as const;

export const KAPSAM_SECENEKLERI = [
  'girisUyelik',
  'odeme',
  'cokDil',
  'yonetimPaneli',
  'entegrasyon',
  'seoReklam',
] as const;

export const ZAMAN_SECENEKLERI = ['acil', 'ceyrek', 'yarim', 'esnek'] as const;
export const BUTCE_SECENEKLERI = ['baslangic', 'orta', 'genis', 'belirsiz'] as const;

/**
 * Talep metninden ilk tahmini çıkarır.
 *
 * Tahmin, doldurulmuş bir formun yerine geçmiyor: yönetici modalda
 * düzeltiyor. Amacı yalnızca sıfırdan başlamamak. Keşif sihirbazından
 * gelen taleplerde metin zaten sihirbazın ürettiği özet olduğu için
 * eşleşme yüksek; elle yazılmış mesajlarda düşük olabilir, sorun değil.
 */
export function metindenTahmin(metin: string): Partial<BriefGirdisi> {
  const m = (metin || '').toLocaleLowerCase('tr');
  const gecer = (...kelimeler: string[]) => kelimeler.some((k) => m.includes(k));

  let amac = '';
  if (gecer('e-ticaret', 'eticaret', 'mağaza', 'magaza', 'satış sitesi')) amac = 'eticaret';
  else if (gecer('saas', 'abonelik', 'panel yazılımı')) amac = 'saas';
  else if (gecer('mobil', 'uygulama', 'ios', 'android')) amac = 'mobil';
  else if (gecer('yenile', 'mevcut site', 'var olan')) amac = 'mevcut';
  else if (gecer('web sitesi', 'kurumsal', 'tanıtım')) amac = 'website';

  const kapsam: string[] = [];
  if (gecer('üyelik', 'uyelik', 'giriş', 'giris', 'login')) kapsam.push('girisUyelik');
  if (gecer('ödeme', 'odeme', 'kredi kartı', 'iyzico', 'stripe')) kapsam.push('odeme');
  if (gecer('çok dil', 'cok dil', 'ingilizce', 'dil desteği')) kapsam.push('cokDil');
  if (gecer('yönetim paneli', 'yonetim paneli', 'admin')) kapsam.push('yonetimPaneli');
  if (gecer('entegrasyon', 'api', 'muhasebe', 'erp')) kapsam.push('entegrasyon');
  if (gecer('seo', 'reklam', 'google ads', 'pazarlama')) kapsam.push('seoReklam');

  let zaman = '';
  if (gecer('acil', 'en kısa', 'en kisa', 'hemen')) zaman = 'acil';
  else if (gecer('esnek', 'acelesi yok')) zaman = 'esnek';

  return { amac, kapsam, zaman };
}

/**
 * Talep kaydında saklanan hâli: seçimler + üretilen metin birlikte.
 *
 * Seçimleri de saklıyoruz; brief'i tekrar açan kişi hangi varsayımlarla
 * üretildiğini görebilsin, gerekirse bir seçimi düzeltip yeniden üretsin.
 */
export interface SaklananBrief {
  girdi: BriefGirdisi;
  brief: Brief;
  tarih: string;
}

/** Talepteki `brief` sütununu okur; bozuksa yok sayar. */
export function saklananiCoz(ham?: string | null): SaklananBrief | null {
  if (!ham) return null;
  try {
    const v = JSON.parse(ham) as Partial<SaklananBrief>;
    if (!v.brief || !Array.isArray(v.brief.roller) || !v.girdi) return null;
    return { girdi: v.girdi, brief: v.brief, tarih: v.tarih || '' };
  } catch {
    // Elle düzenlenmiş ya da eski biçimdeki içeriği sessizce yok sayıyoruz:
    // brief kaybolmuş olur, panel çalışmaya devam eder.
    return null;
  }
}

/** Brief'in yazilabildigi tablolar. Ikisinde de `brief` sutunu var. */
export type KayitTuru = 'inquiries' | 'projects';

/**
 * Üretilen brief'i kayda yazar. Hata yutuluyor — kayıt zorunlu değil.
 *
 * Aynı metin hem talepte hem projede durabiliyor: biri satışın kaydı,
 * diğeri işin kaydı. Talep "çevrildi" olarak kapanıp listede geriye
 * kaydığı için, iş başladıktan sonra brief'e projeden ulaşmak gerekiyor.
 */
export async function briefiSakla(
  kayitTuru: KayitTuru,
  kayitId: number | string,
  girdi: BriefGirdisi,
  brief: Brief,
): Promise<boolean> {
  try {
    const paket: SaklananBrief = { girdi, brief, tarih: new Date().toISOString() };
    await client.entities[kayitTuru].update({
      id: String(kayitId),
      data: { brief: JSON.stringify(paket) },
    });
    return true;
  } catch {
    return false;
  }
}

export async function briefUret(girdi: BriefGirdisi): Promise<Brief> {
  const yanit = (await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/kesif-brief',
    data: girdi,
  })) as unknown;

  // SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz.
  const govde = (
    yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)
      ? (yanit as { data: unknown }).data
      : yanit
  ) as Partial<Brief> | undefined;

  if (!govde || !Array.isArray(govde.roller)) {
    throw new Error('Brief okunamadı.');
  }

  return {
    baslik: govde.baslik || '',
    kunye: govde.kunye || '',
    roller: govde.roller,
    zincir: govde.zincir || '',
  };
}
