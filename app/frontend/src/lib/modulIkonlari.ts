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
  FileCheck2,
  FileSignature,
  FileText,
  FolderOpen,
  Gauge,
  Handshake,
  History,
  LayoutTemplate,
  Lightbulb,
  Link2,
  ListChecks,
  Mail,
  Megaphone,
  MessageSquare,
  MessagesSquare,
  QrCode,
  Receipt,
  ShieldCheck,
  Timer,
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
  FileCheck2,
  FileSignature,
  FileText,
  FolderOpen,
  Gauge,
  Handshake,
  History,
  LayoutTemplate,
  Lightbulb,
  Link2,
  ListChecks,
  Mail,
  Megaphone,
  MessageSquare,
  MessagesSquare,
  QrCode,
  Receipt,
  ShieldCheck,
  Timer,
  UserCog,
};

export function modulIkonu(ad?: string | null): LucideIcon {
  return (ad && MODUL_IKONLARI[ad]) || Blocks;
}
