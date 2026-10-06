import { Ellipsis, FolderKanban, Globe, LifeBuoy, Puzzle, UserCog, type LucideIcon } from 'lucide-react';
import GrupluMenu, { type MenuOgesi } from '@/components/GrupluMenu';
import { MUSTERI_GRUPLARI, type MusteriGrubu } from '@/lib/musteriMenusu';

const GRUP_IKONU: Record<MusteriGrubu | 'diger', LucideIcon> = {
  projeler: FolderKanban,
  destek: LifeBuoy,
  sitem: Globe,
  araclar: Puzzle,
  hesap: UserCog,
  diger: Ellipsis,
};

interface Props<K extends string> {
  sekmeler: MenuOgesi<K>[];
  aktif: K;
  onSec: (sekme: K) => void;
  rozetler?: Partial<Record<K, number>>;
  /** Düz çubuktaki `data-moduller` (modül bilgisi: sunucu / hata / yukleniyor). */
  modulDurumu: string;
}

/**
 * Kalabalık müşteri panelinin gruplu menüsü (Faz 7M; etiketler ek paket
 * `panelKabugu` › `menu`). Yalnız görünür sekme sayısı `DUZ_MENU_SINIRI`'nı aşınca
 * yükleniyor; az sekmeli müşteride düz çubuk kalır.
 */
export default function MusteriMenusu<K extends string>({ modulDurumu, ...props }: Props<K>) {
  return (
    <GrupluMenu<K, MusteriGrubu>
      {...props}
      tanim={MUSTERI_GRUPLARI}
      ikonlar={GRUP_IKONU}
      paket="panelKabugu.menu"
      kimlik="musteri"
      cubukOznitelikleri={{ 'data-moduller': modulDurumu }}
    />
  );
}
