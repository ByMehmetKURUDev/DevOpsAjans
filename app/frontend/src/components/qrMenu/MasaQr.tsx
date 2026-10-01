import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Loader2, QrCode } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alan, DIS_DUGME, KART, SECIM } from '@/components/qrMenu/ortak';
import { hataMetni, type Magaza, type MenuApi, type MenuMeta } from '@/lib/qrMenu';

/** Faz 4M — menünün QR'ı ve masa numaralı toplu QR (ZIP; Faz 4Q üreticisi). */
export default function MasaQr({ api, meta, magaza }: { api: MenuApi; meta: MenuMeta; magaza: Magaza }) {
  const { t } = useTranslation();
  const [onizleme, setOnizleme] = useState<string | null>(null);
  const [bas, setBas] = useState('1');
  const [bit, setBit] = useState('10');
  const [bicim, setBicim] = useState<'png' | 'svg'>('png');
  const [mesgul, setMesgul] = useState<string | null>(null);

  useEffect(() => {
    let adres: string | null = null;
    let iptal = false;
    api
      .qrBlob(magaza.id, 'png')
      .then((b) => {
        if (iptal) return;
        adres = URL.createObjectURL(b);
        setOnizleme(adres);
      })
      .catch((e) => toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
      if (adres) URL.revokeObjectURL(adres);
    };
  }, [api, magaza.id, t]);

  const is = async (anahtar: string, fn: () => Promise<void>) => {
    setMesgul(anahtar);
    try {
      await fn();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  const basN = Number(bas) || 0;
  const bitN = Number(bit) || 0;
  const aralikGecerli = basN >= 1 && bitN >= basN && bitN - basN + 1 <= meta.en_cok_masa;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]" data-testid="menu-masa-qr">
      <div className={`${KART} flex flex-col items-center gap-3 p-4 sm:p-6`}>
        <div className="flex aspect-square w-full max-w-[260px] items-center justify-center overflow-hidden rounded-xl bg-white p-2">
          {onizleme ? (
            <img src={onizleme} alt={t('qrMenu.qr.onizlemeAlt', { ad: magaza.ad })} width={256} height={256} className="h-full w-full" data-testid="menu-qr-onizleme" />
          ) : (
            <Loader2 className="h-6 w-6 animate-spin text-black/50" aria-hidden="true" />
          )}
        </div>
        <p className="break-all text-center font-mono text-xs text-purple-200" dir="ltr">
          {magaza.adres_url}
        </p>
        <div className="flex gap-2">
          {(['png', 'svg'] as const).map((b) => (
            <Button key={b} size="sm" variant="outline" className={DIS_DUGME} disabled={!!mesgul} onClick={() => void is(b, () => api.qrIndir(magaza.id, b))} data-testid={`menu-qr-indir-${b}`}>
              {mesgul === b ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
              {b.toUpperCase()}
            </Button>
          ))}
        </div>
      </div>
      <div className={`${KART} space-y-4 p-4 sm:p-6`}>
        <h4 className="flex items-center gap-2 font-semibold">
          <QrCode className="h-5 w-5 text-purple-300" aria-hidden="true" />
          {t('qrMenu.qr.masaBaslik')}
        </h4>
        <p className="text-sm text-muted-foreground">{t('qrMenu.qr.masaAciklama')}</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Alan etiket={t('qrMenu.qr.ilkMasa')}>
            <Input value={bas} onChange={(e) => setBas(e.target.value.replace(/\D/g, ''))} inputMode="numeric" dir="ltr" data-testid="menu-masa-bas" />
          </Alan>
          <Alan etiket={t('qrMenu.qr.sonMasa')}>
            <Input value={bit} onChange={(e) => setBit(e.target.value.replace(/\D/g, ''))} inputMode="numeric" dir="ltr" data-testid="menu-masa-bit" />
          </Alan>
          <Alan etiket={t('qrMenu.qr.bicim')}>
            <select className={SECIM} value={bicim} onChange={(e) => setBicim(e.target.value as 'png' | 'svg')}>
              <option value="png">PNG</option>
              <option value="svg">SVG</option>
            </select>
          </Alan>
        </div>
        {!aralikGecerli && <p className="text-xs text-amber-200">{t('qrMenu.hata.masa_araligi', { en_cok: meta.en_cok_masa })}</p>}
        <Button disabled={!aralikGecerli || !!mesgul} className="gap-1.5" onClick={() => void is('zip', () => api.masaZip(magaza.id, basN, bitN, bicim))} data-testid="menu-masa-zip">
          {mesgul === 'zip' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
          {t('qrMenu.qr.zipIndir', { sayi: aralikGecerli ? bitN - basN + 1 : 0 })}
        </Button>
        <p className="text-xs text-muted-foreground">{t('qrMenu.qr.ipucu', { ornek: `${magaza.adres_url}?masa=12` })}</p>
      </div>
    </div>
  );
}
