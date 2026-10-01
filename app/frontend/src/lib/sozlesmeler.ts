import { acikIstek, istek } from '@/lib/belge';

/**
 * Faz 3T — sözleşme ve basit elektronik imza uçları.
 *
 * Bu imza 5070 sayılı Kanun anlamında güvenli elektronik imza DEĞİLDİR;
 * taraflar arasında basit elektronik onay kaydıdır (sayfada ve PDF'te yazıyor).
 * İmza isteği, sayfada gösterilen metnin SHA-256 özetini geri yolluyor; sunucu
 * kendi özetiyle karşılaştırıyor (metin değiştiyse imza reddedilir).
 */

export type SozlesmeDurumu = 'taslak' | 'gonderildi' | 'imzalandi' | 'iptal';
export const SOZLESME_DURUMLARI: SozlesmeDurumu[] = ['taslak', 'gonderildi', 'imzalandi', 'iptal'];

export interface Sozlesme {
  id: number;
  no: string;
  surum: number;
  baslik: string;
  govde: string;
  dil: string;
  durum: SozlesmeDurumu | string;
  baslangic: string | null;
  bitis: string | null;
  taraf_ad: string | null;
  metin_ozeti: string;
  imza_ad: string | null;
  imza_at: string | null;
  imza_metin_ozeti: string | null;
  imza_gorseli_var: boolean;
  teklif_id?: number | null;
  gonderildi_at?: string | null;
  // yönetici
  hesap_email?: string | null;
  taraf_eposta?: string | null;
  sablon_id?: number | null;
  kok_id?: number | null;
  onceki_id?: number | null;
  imza_ip_ozeti?: string | null;
  imza_tarayici?: string | null;
  imza_kanali?: string | null;
  yeni_surum?: boolean;
  // girişsiz / müşteri
  imzalanabilir?: boolean;
  baglanti_durumu?: string;
  alici?: string;
  son_kullanma?: string | null;
}

export interface Sablon {
  id: number;
  baslik: string;
  govde: string;
  baslik_en?: string | null;
  govde_en?: string | null;
  aktif: boolean;
}

export interface SozlesmeGirdisi {
  sablon_id?: number | null;
  teklif_id?: number | null;
  baslik?: string;
  govde?: string;
  dil?: string;
  hesap_email?: string;
  taraf_ad?: string;
  taraf_eposta?: string;
  baslangic?: string;
  bitis?: string;
}

export interface ImzaGirdisi {
  ad_soyad: string;
  onay: boolean;
  metin_ozeti: string;
  imza_png?: string | null;
}

const YONETIM = '/api/v1/sozlesme-yonetim';
const ACIK = '/api/v1/sozlesme';
const MUSTERI = '/api/v1/sozlesmelerim';

export async function sablonlar(): Promise<{ sablonlar: Sablon[]; yer_tutucular: string[]; varsayilan_govde: string }> {
  return istek('GET', `${YONETIM}/sablonlar`);
}
export const sablonEkle = (g: Partial<Sablon>) => istek<Sablon>('POST', `${YONETIM}/sablonlar`, g);
export const sablonGuncelle = (id: number, g: Partial<Sablon>) => istek<Sablon>('PUT', `${YONETIM}/sablonlar/${id}`, g);
export const sablonSil = (id: number) => istek<{ silindi: number }>('DELETE', `${YONETIM}/sablonlar/${id}`);

export async function sozlesmeListesi(filtre: { durum?: string; q?: string } = {}): Promise<Sozlesme[]> {
  const s = new URLSearchParams();
  if (filtre.durum) s.set('durum', filtre.durum);
  if (filtre.q) s.set('q', filtre.q);
  const q = s.toString();
  const g = await istek<Sozlesme[]>('GET', q ? `${YONETIM}?${q}` : YONETIM);
  return Array.isArray(g) ? g : [];
}
export const sozlesmeOlustur = (g: SozlesmeGirdisi) => istek<Sozlesme>('POST', YONETIM, g);
export const sozlesmeGuncelle = (id: number, g: SozlesmeGirdisi) => istek<Sozlesme>('PUT', `${YONETIM}/${id}`, g);
export const sozlesmeSil = (id: number) => istek<{ silindi: number }>('DELETE', `${YONETIM}/${id}`);
export const sozlesmeIptal = (id: number) => istek<Sozlesme>('POST', `${YONETIM}/${id}/iptal`);
export const sozlesmeGonder = (id: number, eposta_gonder: boolean) =>
  istek<{ sozlesme: Sozlesme; baglanti: string; eposta_gonderildi: boolean }>('POST', `${YONETIM}/${id}/gonder`, { eposta_gonder });
export const sozlesmeSurumleri = async (id: number) => {
  const g = await istek<Sozlesme[]>('GET', `${YONETIM}/${id}/surumler`);
  return Array.isArray(g) ? g : [];
};
export const yoneticiSozlesmePdf = (id: number) => `${YONETIM}/${id}/pdf`;

// Girişsiz
export const acikSozlesme = (jeton: string) => acikIstek<Sozlesme>('GET', `${ACIK}/${encodeURIComponent(jeton)}`);
export const acikSozlesmeImza = (jeton: string, g: ImzaGirdisi) =>
  acikIstek<Sozlesme>('POST', `${ACIK}/${encodeURIComponent(jeton)}/imza`, g);
export const acikSozlesmePdf = (jeton: string) => `${ACIK}/${encodeURIComponent(jeton)}/pdf`;

// Müşteri
export async function sozlesmelerim(): Promise<Sozlesme[]> {
  const g = await istek<Sozlesme[]>('GET', MUSTERI);
  return Array.isArray(g) ? g : [];
}
export const sozlesmemImza = (id: number, g: ImzaGirdisi) => istek<Sozlesme>('POST', `${MUSTERI}/${id}/imza`, g);
export const sozlesmemPdf = (id: number) => `${MUSTERI}/${id}/pdf`;

export function sozlesmeDurumRengi(durum: string): string {
  switch (durum) {
    case 'imzalandi':
      return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300';
    case 'gonderildi':
      return 'border-sky-400/30 bg-sky-500/10 text-sky-300';
    case 'iptal':
      return 'border-red-400/30 bg-red-500/10 text-red-300';
    default:
      return 'border-white/15 bg-white/5 text-muted-foreground';
  }
}
