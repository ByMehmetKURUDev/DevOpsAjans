import { useEffect, type ReactNode } from 'react';
import {
  AlertTriangle,
  Facebook,
  Globe,
  Instagram,
  Linkedin,
  Loader2,
  Mail,
  MapPin,
  Music2,
  Newspaper,
  Pin,
  Twitter,
  X,
  Youtube,
  type LucideIcon,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Olcum, Uyari } from '@/lib/icerikStudyosu';

/** Faz 5I — İçerik stüdyosu panelinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const GIRDI =
  'h-10 w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SECIM =
  'h-10 w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[96px] w-full min-w-0 rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const DIS_DUGME = 'gap-1.5 !bg-transparent border-white/20';

export const KANAL_IKONU: Record<string, LucideIcon> = {
  instagram: Instagram,
  facebook: Facebook,
  linkedin: Linkedin,
  x: Twitter,
  tiktok: Music2,
  youtube_shorts: Youtube,
  google_isletme: MapPin,
  pinterest: Pin,
  blog: Newspaper,
  email: Mail,
};

export const DURUM_RENGI: Record<string, string> = {
  taslak: 'border-white/15 bg-white/[0.06] text-white/80',
  incelemede: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  musteri_onayi: 'border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-200',
  onaylandi: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  yayinlandi: 'border-purple-400/30 bg-purple-400/15 text-purple-100',
  reddedildi: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
};

export function KanalIkonu({ kanal, className = 'h-3.5 w-3.5' }: { kanal: string; className?: string }) {
  const { t } = useTranslation();
  const Ikon = KANAL_IKONU[kanal] ?? Globe;
  return <Ikon className={className} aria-label={t(`icerikOnay.kanal.${kanal}`, { defaultValue: kanal })} role="img" />;
}

export function Rozet({ children, renk = 'border-white/10 bg-white/[0.05] text-muted-foreground', testid, title }: { children: ReactNode; renk?: string; testid?: string; title?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] ${renk}`} data-testid={testid} title={title}>
      {children}
    </span>
  );
}

export function DurumRozeti({ durum }: { durum: string }) {
  const { t } = useTranslation();
  return (
    <Rozet renk={DURUM_RENGI[durum] ?? DURUM_RENGI.taslak} testid="durum-rozeti">
      {t(`icerikOnay.durum.${durum}`, { defaultValue: durum })}
    </Rozet>
  );
}

/** Uyarı rozeti (sağlık/finans/hukuk vaadi, kaynaksız sayı, yasaklı kelime) — engellemez, insan bakar. */
export function Uyarilar({ uyarilar }: { uyarilar: Uyari[] }) {
  const { t } = useTranslation();
  if (!uyarilar?.length) return null;
  return (
    <div className="flex flex-wrap gap-1" data-testid="uyari-rozetleri">
      {uyarilar.map((u) => (
        <Rozet key={u.tur} renk="border-amber-400/40 bg-amber-400/10 text-amber-100" title={u.eslesen.join(', ')} testid={`uyari-${u.tur}`}>
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          {t(`icerikStudyosu.uyari.${u.tur}`, { defaultValue: u.tur })}
          {u.eslesen.length > 0 && <span className="max-w-[10rem] truncate opacity-80">· {u.eslesen.slice(0, 2).join(', ')}</span>}
        </Rozet>
      ))}
    </div>
  );
}

export function SayacRozeti({ olcum, dil }: { olcum: Olcum | null | undefined; dil: string }) {
  const { t } = useTranslation();
  if (!olcum) return null;
  const f = (n: number) => new Intl.NumberFormat(dil).format(n);
  return (
    <span className={`text-[11px] tabular-nums ${olcum.asim || olcum.hashtag_asim ? 'text-rose-300' : 'text-muted-foreground'}`} data-asim={olcum.asim ? '1' : '0'}>
      {olcum.sinir ? `${f(olcum.uzunluk)} / ${f(olcum.sinir)}` : f(olcum.uzunluk)}
      {olcum.hashtag_sinir != null && olcum.hashtag ? ` · # ${olcum.hashtag}/${olcum.hashtag_sinir}` : ''}
      {(olcum.asim || olcum.hashtag_asim) && <span className="sr-only"> {t('icerikOnay.sinirAsimi')}</span>}
    </span>
  );
}

export function Alan({ etiket, ipucu, children, className }: { etiket: ReactNode; ipucu?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`block min-w-0 text-sm ${className ?? ''}`}>
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      {children}
      {ipucu && <span className="mt-1 block text-xs text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

export const Yukleniyor = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
  </div>
);

export function Bos({ children, testid }: { children: ReactNode; testid?: string }) {
  return (
    <p className="rounded-xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-muted-foreground" data-testid={testid}>
      {children}
    </p>
  );
}

/** Sağdan açılan çekmece (mobilde tam ekran); Esc ile kapanır. */
export function Cekmece({
  baslik,
  onKapat,
  children,
  testid,
  genis = false,
}: {
  baslik: ReactNode;
  onKapat: () => void;
  children: ReactNode;
  testid?: string;
  genis?: boolean;
}) {
  const { t } = useTranslation();
  useEffect(() => {
    const tus = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onKapat();
    };
    window.addEventListener('keydown', tus);
    return () => window.removeEventListener('keydown', tus);
  }, [onKapat]);
  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-background/70 backdrop-blur-sm" onClick={onKapat}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${testid || 'cekmece'}-baslik`}
        className={`h-full w-full overflow-y-auto border-s border-white/10 bg-background p-4 shadow-2xl sm:p-6 ${genis ? 'sm:max-w-3xl' : 'sm:max-w-xl'}`}
        onClick={(e) => e.stopPropagation()}
        data-testid={testid}
      >
        <header className="mb-4 flex items-start gap-3">
          <h3 id={`${testid || 'cekmece'}-baslik`} className="min-w-0 flex-1 break-words text-lg font-bold">
            {baslik}
          </h3>
          <button type="button" className="rounded-lg p-2 hover:bg-white/5" onClick={onKapat} aria-label={t('icerikStudyosu.kapat')} data-testid="cekmece-kapat">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>
        {children}
      </aside>
    </div>
  );
}

export function satirlar(s: string): string[] {
  return s
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean);
}
