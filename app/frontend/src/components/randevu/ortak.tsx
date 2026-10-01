import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import type { Aralik, Haftalik } from '@/lib/randevuOrtak';
import { haftaGunleri } from '@/lib/randevuOrtak';

/** Faz 5R — randevu panelinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[84px] w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const SAAT_GIRDISI =
  'h-9 w-[6.5rem] rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const DIS_DUGME = 'gap-1.5 !bg-transparent border-white/20';

export function Alan({ etiket, ipucu, children, className }: { etiket: string; ipucu?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block text-sm ${className ?? ''}`}>
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      {children}
      {ipucu && <span className="mt-1 block text-xs text-muted-foreground">{ipucu}</span>}
    </label>
  );
}

export function Anahtar({ acik, onDegis, etiket, testid, devreDisi }: { acik: boolean; onDegis: (v: boolean) => void; etiket: string; testid?: string; devreDisi?: boolean }) {
  return (
    <label className={`flex cursor-pointer items-center gap-2 text-sm ${devreDisi ? 'opacity-50' : ''}`}>
      <input type="checkbox" className="h-4 w-4 accent-purple-500" checked={acik} disabled={devreDisi} onChange={(e) => onDegis(e.target.checked)} data-testid={testid} />
      <span>{etiket}</span>
    </label>
  );
}

export function Rozet({ children, renk = 'border-white/10 bg-white/[0.05] text-muted-foreground', testid }: { children: ReactNode; renk?: string; testid?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${renk}`} data-testid={testid}>
      {children}
    </span>
  );
}

export const Yukleniyor = () => (
  <div className="flex items-center justify-center py-16 text-muted-foreground">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
  </div>
);

export function sayiYaz(n: number, dil: string): string {
  try {
    return new Intl.NumberFormat(dil).format(n);
  } catch {
    return String(n);
  }
}

/** Panoya kopyala (yedekli). */
export async function kopyala(metin: string, basari: string, hata: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(metin);
      toast.success(basari);
      return;
    }
  } catch {
    /* yedeğe düş */
  }
  toast.error(hata);
}

/** Dakika → "2 sa" / "45 dk" / "1 gün" (panel etiketleri). */
export function sureYaz(t: (k: string, o?: Record<string, unknown>) => string, dk: number): string {
  if (dk >= 1440 && dk % 1440 === 0) return t('randevu.sure.gun', { sayi: dk / 1440 });
  if (dk >= 60 && dk % 60 === 0) return t('randevu.sure.saat', { sayi: dk / 60 });
  return t('randevu.sure.dk', { sayi: dk });
}

/** Aralık listesi düzenleyici (09:00–12:00, 13:00–18:00 …). */
export function AralikDuzenleyici({
  araliklar,
  onDegis,
  enCok = 4,
  testid,
}: {
  araliklar: Aralik[];
  onDegis: (a: Aralik[]) => void;
  enCok?: number;
  testid?: string;
}) {
  const { t } = useTranslation();
  const degistir = (i: number, j: 0 | 1, deger: string) => {
    const yeni = araliklar.map((a) => [...a] as Aralik);
    yeni[i][j] = deger;
    onDegis(yeni);
  };
  return (
    <div className="flex flex-col gap-1.5" data-testid={testid}>
      {araliklar.map((a, i) => (
        <div key={i} className="flex flex-wrap items-center gap-1.5">
          <input type="time" className={SAAT_GIRDISI} value={a[0]} onChange={(e) => degistir(i, 0, e.target.value)} aria-label={t('randevu.uygunluk.bas')} step={300} />
          <span className="text-muted-foreground" aria-hidden="true">
            –
          </span>
          <input type="time" className={SAAT_GIRDISI} value={a[1] === '24:00' ? '23:59' : a[1]} onChange={(e) => degistir(i, 1, e.target.value)} aria-label={t('randevu.uygunluk.bit')} step={300} />
          {a[1] !== '' && a[1] <= a[0] && <span className="text-[11px] text-amber-300">{t('randevu.uygunluk.ertesiGun')}</span>}
          <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label={t('randevu.sil')} onClick={() => onDegis(araliklar.filter((_, k) => k !== i))}>
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      ))}
      {araliklar.length < enCok && (
        <button
          type="button"
          className="flex w-fit items-center gap-1 text-xs text-purple-200 hover:underline"
          onClick={() => {
            const son = araliklar[araliklar.length - 1];
            onDegis([...araliklar, son ? [son[1] < '23:00' ? son[1] : '18:00', son[1] < '22:00' ? '22:00' : '23:00'] : ['09:00', '17:00']]);
          }}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          {t('randevu.uygunluk.aralikEkle')}
        </button>
      )}
    </div>
  );
}

/** Haftalık saatler: 7 gün × aralıklar (0 = pazartesi). */
export function HaftalikDuzenleyici({ haftalik, onDegis, testid }: { haftalik: Haftalik; onDegis: (h: Haftalik) => void; testid?: string }) {
  const { t, i18n } = useTranslation();
  const adlar = haftaGunleri(i18n.language || 'tr');
  return (
    <div className="divide-y divide-white/5" data-testid={testid}>
      {adlar.map((ad, i) => {
        const anahtar = String(i);
        const araliklar = haftalik[anahtar] || [];
        const acik = araliklar.length > 0;
        return (
          <div key={anahtar} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-start" data-gun={anahtar}>
            <label className="flex w-32 flex-none cursor-pointer items-center gap-2 pt-1.5 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-purple-500"
                checked={acik}
                onChange={(e) => {
                  const yeni = { ...haftalik };
                  if (e.target.checked) yeni[anahtar] = [['09:00', '17:00']];
                  else delete yeni[anahtar];
                  onDegis(yeni);
                }}
              />
              <span className="font-medium">{ad}</span>
            </label>
            {acik ? (
              <AralikDuzenleyici
                araliklar={araliklar}
                onDegis={(a) => {
                  const yeni = { ...haftalik };
                  if (a.length) yeni[anahtar] = a;
                  else delete yeni[anahtar];
                  onDegis(yeni);
                }}
              />
            ) : (
              <span className="pt-1.5 text-sm text-muted-foreground">{t('randevu.uygunluk.kapali')}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Panelde saat: sayfanın saat diliminde. */
export function zamanYaz(iso: string | null | undefined, tz: string, dil: string, secenek: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, { ...secenek, timeZone: tz }).format(new Date(iso));
  } catch {
    return iso;
  }
}
