import { client } from '@/lib/sdkClient';

/**
 * Tahsilat uçları.
 *
 * Fatura ile tahsilat ayrı: `invoices` "şu kadar borç var" der, burada
 * dönen `payments` satırı "şu kadarı şu tarihte şu kanaldan geldi" der.
 * Panel ikisini yan yana gösteriyor.
 *
 * Bu uçlar entity değil, o yüzden `client.entities.*` yerine
 * `client.apiCall.invoke` ile çağrılıyor — site taramasında olduğu gibi.
 */

export type OdemeDurumu = 'bekliyor' | 'odendi' | 'basarisiz' | 'iade' | 'iptal';

export interface Odeme {
  id: number;
  invoice_id?: number | null;
  invoice_no?: string | null;
  client_email?: string | null;
  jeton?: string | null;
  saglayici?: string | null;
  saglayici_ref?: string | null;
  tutar?: number | null;
  para_birimi?: string | null;
  komisyon?: number | null;
  durum?: OdemeDurumu | null;
  hata_mesaji?: string | null;
  odendi_at?: string | null;
  created_at?: string | null;
}

export interface OdemeOzeti {
  tahsil_edilen: number;
  bekleyen: number;
  komisyon: number;
  adet: number;
  /** Kart tahsilatı için anahtarlar Render'da tanımlı mı? */
  saglayici_hazir: boolean;
}

export interface OdemeListesi {
  items: Odeme[];
  ozet: OdemeOzeti;
}

/** SDK bazı uçlarda gövdeyi `data` altında sarmalıyor; ikisini de karşılıyoruz. */
function govdeyiAc<T>(yanit: unknown): T | undefined {
  if (yanit && typeof yanit === 'object' && 'data' in (yanit as Record<string, unknown>)) {
    return (yanit as { data: T }).data;
  }
  return yanit as T | undefined;
}

export async function odemeleriGetir(): Promise<OdemeListesi> {
  const yanit = await client.apiCall.invoke({ method: 'GET', url: '/api/v1/odeme' });
  const govde = govdeyiAc<Partial<OdemeListesi>>(yanit);

  return {
    items: Array.isArray(govde?.items) ? (govde!.items as Odeme[]) : [],
    ozet: {
      tahsil_edilen: govde?.ozet?.tahsil_edilen ?? 0,
      bekleyen: govde?.ozet?.bekleyen ?? 0,
      komisyon: govde?.ozet?.komisyon ?? 0,
      adet: govde?.ozet?.adet ?? 0,
      saglayici_hazir: Boolean(govde?.ozet?.saglayici_hazir),
    },
  };
}

export interface BaglantiSonucu {
  jeton: string;
  adres: string;
  payment_id: number;
}

/**
 * Faturaya ödeme bağlantısı açar.
 *
 * Aynı fatura için bekleyen bağlantı varsa arka uç yenisini üretmiyor,
 * var olanı döndürüyor: müşteriye iki farklı adres giderse hangisinin
 * ödendiği karışır.
 */
export async function odemeBaglantisiUret(invoiceId: number): Promise<BaglantiSonucu> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/odeme/baglanti',
    data: { invoice_id: invoiceId },
  });
  const govde = govdeyiAc<Partial<BaglantiSonucu>>(yanit);
  if (!govde?.jeton) throw new Error('Bağlantı üretilemedi.');

  return {
    jeton: govde.jeton,
    adres: govde.adres || `/ode/${govde.jeton}`,
    payment_id: govde.payment_id ?? 0,
  };
}

/** Elden, havale ya da EFT ile gelen tahsilatı kaydeder. */
export async function elleTahsilatKaydet(girdi: {
  invoiceId: number;
  tutar?: number;
  kanal?: 'elden' | 'havale' | 'eft' | 'diger';
  not?: string;
}): Promise<Odeme> {
  const yanit = await client.apiCall.invoke({
    method: 'POST',
    url: '/api/v1/odeme/elle',
    data: {
      invoice_id: girdi.invoiceId,
      tutar: girdi.tutar,
      kanal: girdi.kanal || 'havale',
      not_: girdi.not,
    },
  });
  const govde = govdeyiAc<Odeme>(yanit);
  if (!govde?.id) throw new Error('Tahsilat kaydedilemedi.');
  return govde;
}

export interface AcikOdeme {
  jeton: string;
  invoice_no?: string | null;
  aciklama?: string | null;
  tutar?: number | null;
  para_birimi?: string | null;
  son_tarih?: string | null;
  durum?: OdemeDurumu | null;
  saglayici_hazir: boolean;
}

/**
 * Müşterinin gördüğü ödeme özeti. Oturum istemiyor: bağlantıyı açan
 * herkes görebiliyor, bu yüzden arka uç ad ve e-posta döndürmüyor.
 */
export async function acikOdemeGetir(jeton: string): Promise<AcikOdeme> {
  const yanit = await client.apiCall.invoke({
    method: 'GET',
    url: `/api/v1/odeme/${encodeURIComponent(jeton)}`,
  });
  const govde = govdeyiAc<Partial<AcikOdeme>>(yanit);
  if (!govde?.jeton) throw new Error('Bağlantı bulunamadı.');

  return {
    jeton: govde.jeton,
    invoice_no: govde.invoice_no ?? null,
    aciklama: govde.aciklama ?? null,
    tutar: govde.tutar ?? null,
    para_birimi: govde.para_birimi ?? 'TRY',
    son_tarih: govde.son_tarih ?? null,
    durum: (govde.durum as OdemeDurumu) ?? 'bekliyor',
    saglayici_hazir: Boolean(govde.saglayici_hazir),
  };
}

/** Ödeme bağlantısının tam adresi. */
export function baglantiAdresi(jeton: string): string {
  const koken = typeof window !== 'undefined' ? window.location.origin : '';
  return `${koken}/ode/${jeton}`;
}

/** Tutarı para birimiyle biçimler. */
export function paraBicimle(tutar?: number | null, birim?: string | null): string {
  const deger = typeof tutar === 'number' ? tutar : 0;
  const kod = (birim || 'TRY').toUpperCase();
  try {
    return new Intl.NumberFormat('tr-TR', {
      style: 'currency',
      currency: kod,
      maximumFractionDigits: 2,
    }).format(deger);
  } catch {
    // Tanınmayan para birimi kodu: sayıyı ve kodu düz yaz.
    return `${deger.toLocaleString('tr-TR')} ${kod}`;
  }
}
