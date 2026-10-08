import { acikIstek, BelgeHatasi, istek, pdfIndir } from '@/lib/belge';

/**
 * Faz 6T — toplantılar uçları ve zaman yardımcıları.
 *
 * * Yönetici `/api/v1/toplantilar`: liste, meta, oluştur/düzenle, davet, ertele, iptal, yapıldı, tutanak, paylaş,
 *   aksiyonlar (+ göreve dönüştür), ICS/PDF/Markdown, müşteri talepleri, ekip takvim abonelikleri.
 * * Müşteri `/api/v1/toplantilarim`: liste, ayrıntı, yanıt, aksiyon tamamla, "Toplantı iste", takvim aboneliği.
 * * Girişsiz `/api/v1/toplanti-yanit`: imzalı yanıt bağlantısı (jeton POST gövdesinde).
 *
 * Zaman: sunucu UTC saklar; panel Europe/Istanbul gösterir, tarayıcının saat dilimi farklıysa ikisini de.
 */

export { BelgeHatasi as ToplantiHatasi };
export { SAAT_DILIMI, ciftZaman, haftaBasi, istanbulGirdisi, istanbulMu, tarayiciSaatDilimi, yerelAd, yereldenUtc, zamanYaz } from '@/lib/toplantiZaman';
export type Durum = 'planlandi' | 'yapildi' | 'ertelendi' | 'iptal';
export type Kategori = 'yaklasan' | 'gecmis' | 'iptal';
export type YerTuru = 'cevrimici' | 'yuz_yuze' | 'telefon';
export type Yanit = 'bekliyor' | 'katilacak' | 'katilamayacak' | 'belki';
export const YANITLAR: Yanit[] = ['katilacak', 'katilamayacak', 'belki'];
export const YER_TURLERI: YerTuru[] = ['cevrimici', 'yuz_yuze', 'telefon'];

export interface Katilimci {
  id?: number;
  tur: 'ekip' | 'dis';
  eposta?: string;
  ad?: string | null;
  yanit?: Yanit;
  yanit_notu?: string | null;
  yanit_at?: string | null;
  yanit_kaynagi?: string | null;
  davet_at?: string | null;
  ben?: boolean;
}

export interface Aksiyon {
  id: number;
  metin: string;
  sorumlu_tur: 'ekip' | 'musteri';
  sorumlu_eposta: string | null;
  son_tarih: string | null;
  durum: 'acik' | 'tamamlandi';
  tamamlandi_at: string | null;
  tamamlayan_eposta: string | null;
  gorev_id: number | null;
  isaretleyebilir?: boolean;
}

export interface Ozet {
  id: number;
  baslik: string;
  baslangic: string;
  bitis: string;
  sure_dk: number;
  yer_turu: YerTuru;
  baglanti: string | null;
  adres: string | null;
  telefon: string | null;
  hesap_email: string | null;
  hesap_adi?: string | null;
  proje_id: number | null;
  crm_aday_id: number | null;
  durum: Durum;
  kategori: Kategori;
  sira_no: number;
  davet_gonderildi_at: string | null;
  guncelleme_bekliyor: boolean;
  notlar_paylasildi: boolean;
  notlar_var: boolean;
  katilimci_sayisi: number;
  yanitlar: Record<Yanit, number>;
  ekip: string[];
  hafta?: string;
}

export interface Cakisma {
  eposta: string;
  toplanti_id: number;
  baslik: string;
  baslangic: string;
  sure_dk: number;
}

export interface Ayrinti extends Ozet {
  gundem: string[];
  iptal_nedeni: string | null;
  notlar: string;
  notlar_html: string;
  kararlar: string[];
  paylasildi_at: string | null;
  yapildi_at: string | null;
  talep_id: number | null;
  katilimcilar: Katilimci[];
  aksiyonlar: Aksiyon[];
  proje: { id: number; baslik: string } | null;
  aday: { id: number; ad: string; email: string | null; firma: string | null } | null;
  cakismalar?: Cakisma[];
  davet?: { gonderilen?: number; eposta?: number; guncelleme?: boolean; hata?: string } | null;
}

export interface Meta {
  ekip: { ad: string; email: string }[];
  musteriler: { eposta: string; ad: string | null }[];
  projeler: { id: number; baslik: string; hesap_email: string }[];
  adaylar: { id: number; ad: string; email: string | null; firma: string | null }[];
  saat_dilimi: string;
  sinirlar: { sure_en_az: number; sure_en_cok: number; katilimci: number; gundem: number };
}

export interface Talep {
  id: number;
  hesap_email: string;
  hesap_adi?: string | null;
  kisi_email: string;
  konu: string;
  araliklar: { bas: string; bit: string }[];
  not: string | null;
  durum: 'bekliyor' | 'planlandi' | 'kapandi';
  toplanti_id: number | null;
  created_at: string | null;
}

export interface Abonelik {
  var: boolean;
  tur?: string;
  created_at?: string | null;
  son_erisim_at?: string | null;
  adres?: string;
}

export interface MusteriOzet {
  id: number;
  baslik: string;
  baslangic: string;
  bitis: string;
  sure_dk: number;
  yer_turu: YerTuru;
  baglanti: string | null;
  adres: string | null;
  telefon: string | null;
  durum: Durum;
  kategori: Kategori;
  iptal_nedeni: string | null;
  katilimci_miyim: boolean;
  yanitim: Yanit | null;
  yanit_notum: string | null;
  notlar_paylasildi: boolean;
  acik_aksiyon?: number;
}

export interface MusteriAyrinti extends MusteriOzet {
  gundem: string[];
  katilimcilar: Katilimci[];
  dis_sayisi: number;
  notlar_html: string | null;
  kararlar: string[];
  aksiyonlar: Aksiyon[];
}

export interface AcikToplanti {
  baslik: string;
  baslangic: string;
  bitis: string;
  sure_dk: number;
  yer_turu: YerTuru;
  baglanti: string | null;
  adres: string | null;
  telefon: string | null;
  gundem: string[];
  durum: Durum;
  ad: string | null;
  eposta: string;
  yanit: Yanit;
  yanit_notu: string | null;
  yanit_at: string | null;
}

const Y = '/api/v1/toplantilar';
const M = '/api/v1/toplantilarim';

// --- Yönetici -------------------------------------------------------------------------------
export const meta = () => istek<Meta>('GET', `${Y}/meta`);
export function liste(p: Record<string, string | number | undefined>) {
  const q = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== null) q.set(k, String(v));
  });
  return istek<{ items: Ozet[]; bekleyen_talep: number }>('GET', `${Y}?${q.toString()}`);
}
export const ayrinti = (id: number) => istek<Ayrinti>('GET', `${Y}/${id}`);
export const olustur = (g: Record<string, unknown>) => istek<Ayrinti>('POST', Y, g);
export const guncelle = (id: number, g: Record<string, unknown>) => istek<Ayrinti>('PUT', `${Y}/${id}`, g);
export const sil = (id: number) => istek<{ ok: boolean }>('DELETE', `${Y}/${id}`);
export const davetGonder = (id: number) => istek<Ayrinti>('POST', `${Y}/${id}/davet`, {});
export const ertele = (id: number, g: Record<string, unknown>) => istek<Ayrinti>('POST', `${Y}/${id}/ertele`, g);
export const iptalEt = (id: number, neden: string) => istek<Ayrinti>('POST', `${Y}/${id}/iptal`, { neden });
export const yapildi = (id: number) => istek<Ayrinti>('POST', `${Y}/${id}/yapildi`, {});
export const tutanakYaz = (id: number, g: { notlar?: string; kararlar?: string[] }) => istek<Ayrinti>('PUT', `${Y}/${id}/tutanak`, g);
export const paylas = (id: number, paylas_: boolean) => istek<Ayrinti>('POST', `${Y}/${id}/paylas`, { paylas: paylas_ });
export const aksiyonEkle = (id: number, g: Record<string, unknown>) => istek<Aksiyon>('POST', `${Y}/${id}/aksiyonlar`, g);
export const aksiyonGuncelle = (aid: number, g: Record<string, unknown>) => istek<Aksiyon>('PUT', `${Y}/aksiyonlar/${aid}`, g);
export const aksiyonSil = (aid: number) => istek<{ ok: boolean }>('DELETE', `${Y}/aksiyonlar/${aid}`);
export const goreveDonustur = (aid: number) => istek<{ gorev_id: number; proje_id: number }>('POST', `${Y}/aksiyonlar/${aid}/gorev`, {});
export const cakismaDenetle = (g: Record<string, unknown>) => istek<{ cakismalar: Cakisma[] }>('POST', `${Y}/cakisma`, g);
export const jitsi = () => istek<{ baglanti: string }>('GET', `${Y}/jitsi`);
export const talepler = (durum?: string) => istek<{ items: Talep[] }>('GET', `${Y}/talepler${durum ? `?durum=${durum}` : ''}`);
export const talepGetir = (id: number) => istek<Talep>('GET', `${Y}/talepler/${id}`);
export const talepKapat = (id: number) => istek<Talep>('POST', `${Y}/talepler/${id}/kapat`, {});
export const abonelikler = () =>
  istek<{ items: ({ ad: string | null; email: string; tur: string; ben: boolean } & Abonelik)[] }>('GET', `${Y}/abonelikler`);
export const abonelikUret = (eposta: string) => istek<Abonelik>('POST', `${Y}/abonelikler`, { eposta });
export const abonelikIptal = (eposta: string) => istek<{ iptal: boolean }>('POST', `${Y}/abonelikler/iptal`, { eposta });
export const pdfAl = (id: number, dil: string) => pdfIndir(`${Y}/${id}/pdf?dil=${dil}`, `toplanti-tutanagi-${id}.pdf`);
export const mdAl = (id: number, dil: string) => pdfIndir(`${Y}/${id}/md?dil=${dil}`, `toplanti-tutanagi-${id}.md`);
export const icsAl = (id: number) => pdfIndir(`${Y}/${id}/ics`, `toplanti-${id}.ics`);

// --- Müşteri --------------------------------------------------------------------------------
export const mOzet = () => istek<{ toplanti: number; talep: number; yaklasan: number }>('GET', `${M}/ozet`);
export const mListe = () => istek<{ items: MusteriOzet[] }>('GET', M);
export const mAyrinti = (id: number) => istek<MusteriAyrinti>('GET', `${M}/${id}`);
export const mYanit = (id: number, yanit: Yanit, not_?: string) =>
  istek<{ yanit: Yanit; yanit_notu: string | null }>('POST', `${M}/${id}/yanit`, { yanit, not: not_ || null });
export const mAksiyon = (aid: number, tamam: boolean) => istek<{ durum: string }>('POST', `${M}/aksiyonlar/${aid}/tamamla`, { tamam });
export const mTalepler = () => istek<{ items: Talep[] }>('GET', `${M}/talepler`);
export const mTalepGonder = (g: { konu: string; araliklar: { bas: string; bit: string }[]; not?: string }) =>
  istek<Talep>('POST', `${M}/talepler`, g);
export const mTakvim = () => istek<Abonelik>('GET', `${M}/takvim`);
export const mTakvimUret = () => istek<Abonelik>('POST', `${M}/takvim`, {});
export const mTakvimIptal = () => istek<{ iptal: boolean }>('DELETE', `${M}/takvim`);
export const mIcs = (id: number) => pdfIndir(`${M}/${id}/ics`, `toplanti-${id}.ics`);
export const mPdf = (id: number, dil: string) => pdfIndir(`${M}/${id}/pdf?dil=${dil}`, `toplanti-tutanagi-${id}.pdf`);
export const mMd = (id: number, dil: string) => pdfIndir(`${M}/${id}/md?dil=${dil}`, `toplanti-tutanagi-${id}.md`);

// --- Girişsiz -------------------------------------------------------------------------------
export const acikOku = (jeton: string) => acikIstek<AcikToplanti>('GET', `/api/v1/toplanti-yanit/${encodeURIComponent(jeton)}`);
export const acikYanit = (jeton: string, yanit: Yanit, not_?: string) =>
  acikIstek<AcikToplanti>('POST', '/api/v1/toplanti-yanit', { jeton, yanit, not: not_ || null });

/** Tahmin edilemez Jitsi oda adı (YALNIZ metin bağlantı: iframe/betik yok). */
export function jitsiUret(): string {
  try {
    const b = new Uint8Array(16);
    crypto.getRandomValues(b);
    return `https://meet.jit.si/mk-${[...b].map((x) => x.toString(16).padStart(2, '0')).join('')}`;
  } catch {
    return '';
  }
}

export function hataKodu(h: unknown): string {
  return h instanceof BelgeHatasi ? h.kod : 'genel';
}
