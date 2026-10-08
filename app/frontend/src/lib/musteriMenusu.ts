/**
 * Müşteri paneli menüsü (Faz 7M).
 *
 * Müşteri paneline modüller açıldıkça sekme çubuğu 22 sekmeye kadar
 * uzayabiliyor. Görünür sekme sayısı `DUZ_MENU_SINIRI`'nı aşınca menü,
 * yönetici panelindeki gibi gruplu olur (`components/GrupluMenu.tsx`); daha az
 * sekmesi olan müşteride bugünkü düz sekme çubuğu aynen kalır.
 *
 * Sınır neden 10: modülü olmayan bir müşteride bugün 9 sekme var (projeler,
 * faturalar, krediler, destek, mesajlar, raporlar, sitem, site analizi,
 * profil); BETA ve üstü paketlerde Dosyalar ile 10. Bu müşteriler — yani
 * çoğunluk — düz çubukta kalır; ek araç modülleri açıldıkça gruplu menüye
 * geçilir.
 *
 * Faz 7K: sayı sınırın altında kalsa da düz çubuk ekrana sığmıyorsa (dar pencere, uzun dil) gruplu menü
 * (`DUZ_MENU_EN_DAR`).
 *
 * Tanımda adı geçmeyen yeni bir sekme kaybolmaz: "Diğer" grubunda görünür.
 */
import { yerelOku, yerelYaz, type GrupTanimi } from '@/lib/grupluMenu';

export type MusteriGrubu = 'projeler' | 'destek' | 'sitem' | 'araclar' | 'hesap';

/** Görünür sekme sayısı bunu aşarsa gruplu menü. */
export const DUZ_MENU_SINIRI = 10;

/**
 * Faz 7K — düz çubuğun sığma denetimi bu genişlikten (px) itibaren: sınırın altındaki (≤ 10 sekmeli) müşteride
 * düz çubuk bu genişlikte ve üstünde sığmıyorsa gruplu menü (ClientPanel ölçüyor). Ölçüm (7K): 1024 px'te 9
 * sekme Türkçe 75 px, Almanca 1280/1366'da da 22 px; 10 sekmede 1366'da Türkçe 6, İngilizce 71, Rusça 167,
 * Almanca 235 px taşıyordu — son sekmeler çubuğun yatay kaydırmasında gizli kalıyordu. Ayrıca 1536 px'in
 * altında sekme iç boşluğu daraltıldı (1280–1535: 16 px, 1280 altı: 12 px). Altında (telefon) düz çubuk
 * eskisi gibi yatay kaydırılır.
 */
export const DUZ_MENU_EN_DAR = 768;

/** Grupların ve içlerindeki sekmelerin sırası (tek kaynak; anahtarlar `ClientPanel` `Tab`). */
export const MUSTERI_GRUPLARI: readonly GrupTanimi<MusteriGrubu>[] = [
  // Faz 6T: toplantılar — yalnız hesabın toplantısı ya da toplantı talebi varken görünür (ClientPanel).
  { anahtar: 'projeler', sekmeler: ['projects', 'dosyalar', 'raporlar', 'toplantilar'] },
  { anahtar: 'destek', sekmeler: ['tickets', 'mesajlar', 'asistanlar'] },
  { anahtar: 'sitem', sekmeler: ['sitem', 'analiz'] },
  {
    anahtar: 'araclar',
    sekmeler: [
      'qr',
      'kartvizit',
      'menu',
      'randevu',
      'aiAsistan',
      'icerik',
      'epostaPazarlama',
      'sahaServisi',
      'etkinlik',
      'stokPos',
      'egitim',
      'ik',
      'hukuk',
      'onMuhasebe',
      'hedefler',
      'otomasyon',
      'api',
    ],
  },
  // Faz 5K: "Ortaklık" yalnız onaylı ortakta görünür (kişiye ait; modül değil).
  { anahtar: 'hesap', sekmeler: ['invoices', 'krediler', 'ortaklik', 'profile'] },
];

export function grupluMenuMu(gorunurSekmeSayisi: number): boolean {
  return gorunurSekmeSayisi > DUZ_MENU_SINIRI;
}

/**
 * Son açılan sekme — yönetici panelinden AYRI anahtar. Yalnız gruplu menüde
 * yazılır: düz çubuklu müşteride panel bugünkü gibi Projelerim ile açılır.
 */
const SON_SEKME_ANAHTARI = 'mk_musteri_son_sekme';

export function sonMusteriSekmesi(): string | null {
  return yerelOku(SON_SEKME_ANAHTARI);
}

export function sonMusteriSekmesiniYaz(sekme: string): void {
  yerelYaz(SON_SEKME_ANAHTARI, sekme);
}
