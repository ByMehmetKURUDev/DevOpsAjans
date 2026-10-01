import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';

/** Faz 4A — "API ve webhook" bileşenlerinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const ALAN =
  'w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const ROZET = 'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px]';

/** Panoya kopyala; tarayıcı izin vermezse geçici metin alanıyla dener. */
export async function kopyala(metin: string, basari: string, hata: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(metin);
      toast.success(basari);
      return true;
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
      return true;
    }
  } catch {
    /* yoksay */
  }
  toast.error(hata);
  return false;
}

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

/** Kod / komut bloğu: her zaman soldan sağa, yatay kaydırmalı (sayfa taşmaz), kopyala düğmeli. */
export function KodKutusu({ kod, baslik, testId }: { kod: string; baslik?: string; testId?: string }) {
  const { t } = useTranslation();
  const [kopyalandi, setKopyalandi] = useState(false);
  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-white/10 bg-black/50" data-testid={testId}>
      <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-1.5">
        <span className="truncate text-[11px] uppercase tracking-wider text-muted-foreground">{baslik || ''}</span>
        <button
          type="button"
          className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-purple-200 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
          onClick={async () => {
            if (await kopyala(kod, t('apiErisimi.kopyalandi'), t('apiErisimi.kopyalanamadi'))) {
              setKopyalandi(true);
              window.setTimeout(() => setKopyalandi(false), 1500);
            }
          }}
          aria-label={t('apiErisimi.kopyala')}
        >
          {kopyalandi ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
          {t('apiErisimi.kopyala')}
        </button>
      </div>
      <pre className="max-w-full overflow-x-auto p-3 text-xs leading-relaxed text-slate-200" dir="ltr">
        <code>{kod}</code>
      </pre>
    </div>
  );
}

/** Bir kez gösterilen gizli değer (API anahtarı / webhook sırrı). */
export function BirKezKutusu({
  deger,
  uyari,
  onKapat,
  testId,
}: {
  deger: string;
  uyari: string;
  onKapat: () => void;
  testId: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="rounded-2xl border border-amber-400/40 bg-amber-500/10 p-4" role="alert">
      <p className="text-sm text-amber-100">{uyari}</p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
        <code
          className="min-w-0 flex-1 break-all rounded-md border border-white/10 bg-black/60 px-3 py-2 font-mono text-sm text-white"
          dir="ltr"
          data-testid={testId}
        >
          {deger}
        </code>
        <button
          type="button"
          className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md bg-purple-600 px-3 py-2 text-sm font-medium text-white hover:bg-purple-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-300"
          onClick={() => void kopyala(deger, t('apiErisimi.kopyalandi'), t('apiErisimi.kopyalanamadi'))}
          data-testid={`${testId}-kopyala`}
        >
          <Copy className="h-4 w-4" aria-hidden="true" />
          {t('apiErisimi.kopyala')}
        </button>
      </div>
      <button
        type="button"
        className="mt-3 text-sm text-amber-100 underline-offset-4 hover:underline"
        onClick={onKapat}
        data-testid={`${testId}-kapat`}
      >
        {t('apiErisimi.kopyaladimKapat')}
      </button>
    </div>
  );
}

const DURUM_RENKLERI: Record<string, string> = {
  aktif: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  basarili: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
  bekliyor: 'border-sky-400/30 bg-sky-500/10 text-sky-200',
  pasif: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  atlandi: 'border-white/15 bg-white/[0.05] text-muted-foreground',
  iptal: 'border-red-400/40 bg-red-500/10 text-red-200',
  vazgecildi: 'border-red-400/40 bg-red-500/10 text-red-200',
  suresi_doldu: 'border-amber-400/30 bg-amber-500/10 text-amber-200',
};

export function DurumRozeti({ durum, metin }: { durum: string; metin: string }) {
  return (
    <span className={`${ROZET} ${DURUM_RENKLERI[durum] || DURUM_RENKLERI.pasif}`} data-durum={durum}>
      {metin}
    </span>
  );
}
