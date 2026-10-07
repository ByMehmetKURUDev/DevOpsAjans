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
 * Tanımda adı geçmeyen yeni bir sekme kaybolmaz: "Diğer" grubunda görünür.
 */
import { yerelOku, yerelYaz, type GrupTanimi } from '@/lib/grupluMenu';

export type MusteriGrubu = 'projeler' | 'destek' | 'sitem' | 'araclar' | 'hesap';

/** Görünür sekme sayısı bunu aşarsa gruplu menü. */
export const DUZ_MENU_SINIRI = 10;

/** Grupların ve içlerindeki sekmelerin sırası (tek kaynak; anahtarlar `ClientPanel` `Tab`). */
export const MUSTERI_GRUPLARI: readonly GrupTanimi<MusteriGrubu>[] = [
  { anahtar: 'projeler', sekmeler: ['projects', 'dosyalar', 'raporlar'] },
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
      'otomasyon',
      'api',
    ],
  },
  { anahtar: 'hesap', sekmeler: ['invoices', 'krediler', 'profile'] },
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
