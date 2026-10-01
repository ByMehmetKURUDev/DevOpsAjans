import {
  Activity,
  BarChart3,
  BellRing,
  Blocks,
  BookOpen,
  Bot,
  Boxes,
  Briefcase,
  Bug,
  CalendarClock,
  CalendarDays,
  Coins,
  DollarSign,
  FileText,
  FolderOpen,
  Gauge,
  History,
  Lightbulb,
  Link2,
  ListChecks,
  Mail,
  Megaphone,
  MessageSquare,
  MessagesSquare,
  Receipt,
  ShieldCheck,
  UserCog,
  type LucideIcon,
} from 'lucide-react';

/**
 * Manifestteki `ikon` adı → lucide bileşeni.
 *
 * Bütün lucide paketini içe almamak için yalnız manifestte geçen adlar
 * burada; bilinmeyen ad `Blocks` ile çiziliyor. Manifeste yeni ikon eklenirse
 * buraya da eklenmeli (arka uç testi manifest ikonlarını bu dosyada arıyor).
 */
export const MODUL_IKONLARI: Record<string, LucideIcon> = {
  Activity,
  BarChart3,
  BellRing,
  Blocks,
  BookOpen,
  Bot,
  Boxes,
  Briefcase,
  Bug,
  CalendarClock,
  CalendarDays,
  Coins,
  DollarSign,
  FileText,
  FolderOpen,
  Gauge,
  History,
  Lightbulb,
  Link2,
  ListChecks,
  Mail,
  Megaphone,
  MessageSquare,
  MessagesSquare,
  Receipt,
  ShieldCheck,
  UserCog,
};

export function modulIkonu(ad?: string | null): LucideIcon {
  return (ad && MODUL_IKONLARI[ad]) || Blocks;
}
