import {
  BookText,
  Bug,
  Calculator,
  CalendarCheck,
  FileUp,
  GraduationCap,
  IdCard,
  LifeBuoy,
  Mail,
  MessagesSquare,
  PenTool,
  Plane,
  type LucideIcon,
} from 'lucide-react';

import type { Durum, Kaynak } from '@/lib/gelenKutusu';

/** Faz 5G — gelen kutusu listesi ve ayrıntısının ortak görsel eşlemeleri. */
export const KAYNAK_IKONU: Record<Kaynak, LucideIcon> = {
  iletisim: Mail,
  fiyat_teklifi: Calculator,
  destek: LifeBuoy,
  sohbet: MessagesSquare,
  kartvizit: IdCard,
  randevu: CalendarCheck,
  geri_bildirim: Bug,
  icerik_revizyon: PenTool,
  belge: FileUp,
  egitim: GraduationCap,
  belge_paylasim: BookText,
  izin_talebi: Plane,
};

export const DURUM_RENGI: Record<Durum, string> = {
  yeni: 'bg-pink-400',
  yanit_bekliyor: 'bg-amber-400',
  okundu: 'bg-slate-400',
  kapandi: 'bg-emerald-400',
};
