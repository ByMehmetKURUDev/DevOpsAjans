import { useTranslation } from 'react-i18next';
import {
  CalendarDays,
  Contact,
  Link,
  Link2,
  Mail,
  MapPin,
  MessageCircle,
  MessageSquareText,
  Phone,
  Smartphone,
  Star,
  Type,
  Wifi,
  type LucideIcon,
} from 'lucide-react';
import { toast } from 'sonner';

import type { QrDurumu, QrTuru } from '@/lib/dinamikQr';

/** Faz 4Q — QR bileşenlerinin ortak küçük parçaları. */

export const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';

export const TUR_IKONLARI: Record<QrTuru | 'kisa_link', LucideIcon> = {
  url: Link2,
  google_yorum: Star,
  whatsapp: MessageCircle,
  telefon: Phone,
  eposta: Mail,
  sms: MessageSquareText,
  konum: MapPin,
  vcard: Contact,
  etkinlik: CalendarDays,
  uygulama: Smartphone,
  wifi: Wifi,
  metin: Type,
  kisa_link: Link,
};

const DURUM_RENKLERI: Record<QrDurumu, string> = {
  aktif: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  pasif: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  engelli: 'border-red-400/40 bg-red-500/10 text-red-200',
  suresi_doldu: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
  limit_doldu: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
};

export function DurumRozeti({ durum, statik }: { durum: QrDurumu; statik?: boolean }) {
  const { t } = useTranslation();
  if (statik) {
    return (
      <span className="inline-flex items-center rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-200">
        {t('dinamikQr.statik')}
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] ${DURUM_RENKLERI[durum]}`}
      data-qr-durum={durum}
    >
      {t(`dinamikQr.durum.${durum}`)}
    </span>
  );
}

export function TurRozeti({ tur, kisa }: { tur: QrTuru; kisa?: boolean }) {
  const { t } = useTranslation();
  const anahtar = kisa ? 'kisa_link' : tur;
  const Ikon = TUR_IKONLARI[anahtar];
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-muted-foreground">
      <Ikon className="h-3 w-3" aria-hidden="true" />
      {t(`dinamikQr.tur.${anahtar}`)}
    </span>
  );
}

/** Panoya kopyala; tarayıcı izin vermezse geçici metin alanıyla dener. */
export async function kopyala(metin: string, basari: string, hata: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(metin);
      toast.success(basari);
      return;
    }
  } catch {
    /* aşağıdaki yedeğe düş */
  }
  try {
    const alan = document.createElement('textarea');
    alan.value = metin;
    alan.setAttribute('readonly', '');
    alan.style.position = 'fixed';
    alan.style.opacity = '0';
    document.body.appendChild(alan);
    alan.select();
    const tamam = document.execCommand('copy');
    alan.remove();
    if (tamam) {
      toast.success(basari);
      return;
    }
  } catch {
    /* yoksay */
  }
  toast.error(hata);
}

/** Tarihi seçili dilde kısa biçimde yazar. */
export function tarihYaz(iso: string | null | undefined, dil: string, saatli = true): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, saatli ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(
      new Date(iso)
    );
  } catch {
    return iso;
  }
}

export function sayiYaz(n: number, dil: string): string {
  try {
    return new Intl.NumberFormat(dil).format(n);
  } catch {
    return String(n);
  }
}
