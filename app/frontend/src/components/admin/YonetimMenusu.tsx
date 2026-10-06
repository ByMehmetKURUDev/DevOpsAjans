import {
  Cog,
  Ellipsis,
  FolderKanban,
  Globe,
  Handshake,
  LifeBuoy,
  Megaphone,
  Puzzle,
  Wallet,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import GrupluMenu, { type MenuOgesi } from '@/components/GrupluMenu';
import { GRUPLAR, type GrupAnahtari } from '@/lib/yonetimMenusu';

const GRUP_IKONU: Record<GrupAnahtari, LucideIcon> = {
  site: Globe,
  pazarlama: Megaphone,
  satis: Handshake,
  projeler: FolderKanban,
  finans: Wallet,
  destek: LifeBuoy,
  araclar: Puzzle,
  otomasyon: Workflow,
  sistem: Cog,
  diger: Ellipsis,
};

export type YonetimSekmesi<K extends string> = MenuOgesi<K>;

interface Props<K extends string> {
  sekmeler: YonetimSekmesi<K>[];
  aktif: K;
  onSec: (sekme: K) => void;
  /** Sekme başına sayı rozeti (ör. okunmamış sohbet); grubun rozeti toplamdır. */
  rozetler?: Partial<Record<K, number>>;
  /**
   * Rozeti yalnız kendi düğmesinde görünen, grubun toplamına KATILMAYAN sekmeler (Faz 5G):
   * sohbetler gelen kutusunun sayısında zaten var — Destek grubunda iki kez sayılmasın.
   */
  grubaKatilmayan?: readonly K[];
}

/**
 * Yönetici paneli menüsü: üstte gruplar (`lib/yonetimMenusu.ts` GRUPLAR),
 * altta seçili grubun bölümleri. Düzen ve davranış ortak `GrupluMenu`'de
 * (müşteri paneli de kalabalıklaşınca aynısını kullanıyor).
 */
export default function YonetimMenusu<K extends string>(props: Props<K>) {
  return <GrupluMenu<K, GrupAnahtari> {...props} tanim={GRUPLAR} ikonlar={GRUP_IKONU} paket="yonetimMenusu" kimlik="yonetim" />;
}
