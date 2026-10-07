import { AlertTriangle, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Uyari } from '@/lib/belgeler';

/** Faz 5B — belgeler bileşenlerinin ortak sınıfları ve küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4 sm:p-5';
export const SECIM = 'h-10 w-full rounded-md border border-white/10 bg-white/5 px-3 text-sm text-foreground';
export const ALAN_ETIKETI = 'mb-1 block text-xs text-muted-foreground';

export function Yukleniyor() {
  return (
    <div className="flex items-center justify-center py-16 text-muted-foreground">
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
    </div>
  );
}

export function Rozet({ children, renk = 'slate', testId }: { children: React.ReactNode; renk?: 'slate' | 'emerald' | 'amber' | 'sky' | 'fuchsia'; testId?: string }) {
  const sinif: Record<string, string> = {
    slate: 'border-white/15 bg-white/5 text-slate-200',
    emerald: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
    amber: 'border-amber-400/30 bg-amber-400/10 text-amber-100',
    sky: 'border-sky-400/30 bg-sky-400/10 text-sky-100',
    fuchsia: 'border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-100',
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] leading-4 ${sinif[renk]}`} data-testid={testId}>
      {children}
    </span>
  );
}

/** AI çıktısındaki kural tabanlı uyarılar (ör. girdide olmayan sayı). */
export function AiUyarilari({ uyarilar }: { uyarilar: Uyari[] | undefined }) {
  const { t } = useTranslation();
  if (!uyarilar || uyarilar.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1 text-xs text-amber-100" data-testid="belge-ai-uyari">
      {uyarilar.map((u) => (
        <li key={u.tur} className="flex items-start gap-1.5">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>
            {t(`belgeler.ai.uyari.${u.tur}`, { defaultValue: t('belgeler.ai.uyari.genel') })}
            {u.eslesen.length > 0 && <span className="text-amber-200/80"> — {u.eslesen.join(', ')}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Belge görünümü + yazdırma stilleri. Yazdırırken gövdeye `belge-yazdir` sınıfı eklenir;
 * sayfada yalnız `.belge-yazdir-alani` kalır (beyaz zemin, koyu metin), strateji ızgarası
 * masaüstü düzeninde basılır. Ana CSS'e (ilk açılış paketi) girmesin diye burada.
 */
export function BelgeStilleri() {
  return (
    <style>{`
.belge-icerik li[data-satir] { list-style: none; margin-left: -1.1em; }
.belge-icerik[data-isaretlenebilir="evet"] li[data-satir] { cursor: pointer; border-radius: .375rem; }
.belge-icerik[data-isaretlenebilir="evet"] li[data-satir]:hover { background: rgba(255,255,255,.05); }
.belge-icerik table { display: block; overflow-x: auto; max-width: 100%; }
.belge-icerik pre { overflow-x: auto; }
.strateji-izgara { display: flex; flex-direction: column; gap: .75rem; }
.belge-duzen { display: grid; gap: 1rem; }
@media (min-width: 1024px) { .belge-duzen { grid-template-columns: minmax(260px, 340px) minmax(0, 1fr); } }
.surum-pencere { background: hsl(var(--background)); }
.surum-duzen { display: grid; min-height: 0; }
.surum-liste { max-height: 30vh; border-bottom-width: 1px; }
@media (min-width: 768px) {
  .surum-duzen { grid-template-columns: 260px minmax(0, 1fr); }
  .surum-liste { max-height: none; border-bottom-width: 0; border-right-width: 1px; }
}
@media (min-width: 768px) { .strateji-izgara { display: grid; gap: .75rem; } }
@media print {
  html, body.belge-yazdir { background: #fff !important; }
  body.belge-yazdir * { visibility: hidden; }
  body.belge-yazdir .belge-yazdir-alani, body.belge-yazdir .belge-yazdir-alani * {
    visibility: visible; color: #111 !important; background: transparent !important; box-shadow: none !important;
    text-shadow: none !important; border-color: #c8c8d0 !important; backdrop-filter: none !important; -webkit-backdrop-filter: none !important;
  }
  body.belge-yazdir .belge-yazdir-alani { position: absolute; inset: 0 auto auto 0; width: 100%; padding: 0 10mm; }
  body.belge-yazdir .belge-yazdir-alani .yazdirma { display: none !important; }
  body.belge-yazdir .strateji-izgara { display: grid !important; }
  body.belge-yazdir .strateji-kutu { break-inside: avoid; }
}
`}</style>
  );
}

/** Tarayıcının yazdırma penceresi (yalnız belge alanı basılır). */
export function yazdir(): void {
  const bitir = () => {
    document.body.classList.remove('belge-yazdir');
    window.removeEventListener('afterprint', bitir);
  };
  document.body.classList.add('belge-yazdir');
  window.addEventListener('afterprint', bitir);
  window.print();
  // Bazı tarayıcılar afterprint göndermiyor: güvence.
  window.setTimeout(bitir, 1500);
}

/** "a, b , c" → ["a","b","c"] */
export function etiketleriAyir(metin: string): string[] {
  return metin
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}
