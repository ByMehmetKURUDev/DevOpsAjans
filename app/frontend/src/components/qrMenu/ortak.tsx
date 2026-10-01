import { useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ImagePlus, Languages, Loader2, Sparkles, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { hataMetni, type MenuApi } from '@/lib/qrMenu';
import { DIL_ADLARI, type Ceviriler, type MenuDili, type MenuGorsel } from '@/lib/qrMenuOrtak';

/** Faz 4M — QR menü panelinin ortak küçük parçaları. */

export const KART = 'cam-kart rounded-2xl border border-white/10 bg-white/[0.03]';
export const SECIM =
  'h-10 w-full rounded-md border border-white/10 bg-black/40 px-2 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
export const METIN_ALANI =
  'min-h-[84px] w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400';
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

export function Anahtar({
  acik,
  onDegis,
  etiket,
  testid,
  devreDisi,
}: {
  acik: boolean;
  onDegis: (v: boolean) => void;
  etiket: string;
  testid?: string;
  devreDisi?: boolean;
}) {
  return (
    <label className={`flex cursor-pointer items-center gap-2 text-sm ${devreDisi ? 'opacity-50' : ''}`}>
      <input
        type="checkbox"
        className="h-4 w-4 accent-purple-500"
        checked={acik}
        disabled={devreDisi}
        onChange={(e) => onDegis(e.target.checked)}
        data-testid={testid}
      />
      <span>{etiket}</span>
    </label>
  );
}

/** Görsel seç / yükle / kaldır. Yükleme sunucuda WebP'ye çevriliyor. */
export function GorselSecici({
  api,
  magazaId,
  gorsel,
  onDegis,
  etiket,
  testid,
  enCokMb = 5,
}: {
  api: MenuApi;
  magazaId: number;
  gorsel: MenuGorsel | null;
  onDegis: (g: MenuGorsel | null) => void;
  etiket: string;
  testid?: string;
  enCokMb?: number;
}) {
  const { t } = useTranslation();
  const girdi = useRef<HTMLInputElement>(null);
  const [yukleniyor, setYukleniyor] = useState(false);
  const sec = async (dosya: File | undefined) => {
    if (!dosya) return;
    if (dosya.size > enCokMb * 1024 * 1024) {
      toast.error(t('qrMenu.hata.gorsel_buyuk', { en_cok_mb: enCokMb }));
      return;
    }
    setYukleniyor(true);
    try {
      onDegis(await api.gorselYukle(magazaId, dosya));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setYukleniyor(false);
      if (girdi.current) girdi.current.value = '';
    }
  };
  return (
    <div className="text-sm">
      <span className="mb-1 block font-medium text-white/90">{etiket}</span>
      <div className="flex items-center gap-3">
        <div className="flex h-16 w-16 flex-none items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-black/30">
          {gorsel ? (
            <img src={gorsel.k} alt="" width={64} height={64} className="h-full w-full object-cover" loading="lazy" decoding="async" />
          ) : (
            <ImagePlus className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          )}
        </div>
        <input
          ref={girdi}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => void sec(e.target.files?.[0])}
          data-testid={testid}
        />
        <Button type="button" size="sm" variant="outline" className={DIS_DUGME} onClick={() => girdi.current?.click()} disabled={yukleniyor}>
          {yukleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ImagePlus className="h-4 w-4" aria-hidden="true" />}
          {gorsel ? t('qrMenu.gorsel.degistir') : t('qrMenu.gorsel.yukle')}
        </Button>
        {gorsel && (
          <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label={t('qrMenu.gorsel.kaldir')} onClick={() => onDegis(null)}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        )}
      </div>
      <span className="mt-1 block text-xs text-muted-foreground">{t('qrMenu.gorsel.ipucu', { mb: enCokMb })}</span>
    </div>
  );
}

/** Ek dillerin elle çeviri alanları (ad + isteğe bağlı açıklama). */
export function CeviriAlanlari({
  diller,
  ceviriler,
  onDegis,
  aciklamaVar,
  testid,
}: {
  diller: MenuDili[];
  ceviriler: Ceviriler;
  onDegis: (c: Ceviriler) => void;
  aciklamaVar?: boolean;
  testid?: string;
}) {
  const { t } = useTranslation();
  if (!diller.length) return <p className="text-xs text-muted-foreground">{t('qrMenu.ceviri.ekDilYok')}</p>;
  const yaz = (dil: MenuDili, alan: 'ad' | 'aciklama', deger: string) =>
    onDegis({ ...ceviriler, [dil]: { ...(ceviriler[dil] || {}), [alan]: deger } });
  return (
    <div className="space-y-3" data-testid={testid}>
      {diller.map((dil) => (
        <div key={dil} className="rounded-xl border border-white/10 bg-black/20 p-3" dir={dil === 'ar' ? 'rtl' : 'ltr'}>
          <span className="mb-2 flex items-center gap-1.5 text-xs font-medium text-purple-200">
            <Languages className="h-3.5 w-3.5" aria-hidden="true" />
            {DIL_ADLARI[dil]}
          </span>
          <Input
            value={ceviriler[dil]?.ad || ''}
            onChange={(e) => yaz(dil, 'ad', e.target.value)}
            placeholder={t('qrMenu.ceviri.ad')}
            lang={dil}
            data-testid={testid ? `${testid}-${dil}-ad` : undefined}
          />
          {aciklamaVar && (
            <textarea
              value={ceviriler[dil]?.aciklama || ''}
              onChange={(e) => yaz(dil, 'aciklama', e.target.value)}
              placeholder={t('qrMenu.ceviri.aciklama')}
              className={`${METIN_ALANI} mt-2 min-h-[60px]`}
              lang={dil}
            />
          )}
        </div>
      ))}
    </div>
  );
}

/** "AI ile çevir" düğmesi: anahtar yoksa / bütçe dolduysa kapalı ve nedeni yazılı. */
export function AiCevirDugmesi({
  acik,
  ekDilVar,
  yukleniyor,
  onTikla,
  testid,
}: {
  acik: boolean;
  ekDilVar: boolean;
  yukleniyor: boolean;
  onTikla: () => void;
  testid?: string;
}) {
  const { t } = useTranslation();
  const neden = !ekDilVar ? t('qrMenu.ceviri.ekDilYok') : !acik ? t('qrMenu.ceviri.aiKapali') : undefined;
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button
        type="button"
        size="sm"
        variant="outline"
        className={DIS_DUGME}
        disabled={!acik || !ekDilVar || yukleniyor}
        onClick={onTikla}
        title={neden}
        data-testid={testid}
      >
        {yukleniyor ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
        {t('qrMenu.ceviri.aiIleCevir')}
      </Button>
      {neden && <span className="text-[11px] text-muted-foreground" data-testid={testid ? `${testid}-neden` : undefined}>{neden}</span>}
    </span>
  );
}

export function Rozet({ children, renk = 'border-white/10 bg-white/[0.05] text-muted-foreground', testid }: { children: ReactNode; renk?: string; testid?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${renk}`} data-testid={testid}>
      {children}
    </span>
  );
}

/** Tarihi seçili dilde kısa biçimde yazar. */
export function tarihYaz(iso: string | null | undefined, dil: string, saatli = true): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat(dil, saatli ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(new Date(iso));
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
