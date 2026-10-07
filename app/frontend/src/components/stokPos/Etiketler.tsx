import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Printer, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Barkod } from '@/components/stokPos/ortak';
import { para, type Urun } from '@/lib/stokPos';

/**
 * Faz 6P — A4 barkod etiketi sayfası (SVG barkod, paket yok). İki hazır ölçü: 3 × 8 (70 × 37 mm, 24 etiket)
 * ve 4 × 10 (52,5 × 29,7 mm, 40 etiket). Yazdırma CSS'i yalnız etiket sayfalarını gösterir (`@page A4`).
 */
const OLCULER = {
  '3x8': { sutun: 3, satir: 8, en: 70, boy: 37.125 },
  '4x10': { sutun: 4, satir: 10, en: 52.5, boy: 29.7 },
} as const;
type Olcu = keyof typeof OLCULER;

export default function Etiketler({ urunler, paraBirimi, onKapat }: { urunler: Urun[]; paraBirimi: string; onKapat: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [olcu, setOlcu] = useState<Olcu>('3x8');
  const [adetler, setAdetler] = useState<Record<number, number>>(() => Object.fromEntries(urunler.map((u) => [u.id, 1])));
  const [fiyat, setFiyat] = useState(true);
  const o = OLCULER[olcu];
  const sayfaBasi = o.sutun * o.satir;
  const etiketler = useMemo(() => urunler.flatMap((u) => Array.from({ length: Math.max(0, Math.min(300, adetler[u.id] || 0)) }, () => u)), [urunler, adetler]);
  const sayfalar: Urun[][] = [];
  for (let i = 0; i < etiketler.length; i += sayfaBasi) sayfalar.push(etiketler.slice(i, i + sayfaBasi));
  const stil = `
.mk-etiket-kok{position:fixed;inset:0;z-index:70;overflow:auto;background:rgba(0,0,0,.8);padding:12px}
.mk-etiket-sayfa{width:210mm;height:297mm;background:#fff;color:#000;margin:0 auto 12px;display:grid;grid-template-columns:repeat(${o.sutun},${o.en}mm);grid-template-rows:repeat(${o.satir},${o.boy}mm);box-shadow:0 10px 30px rgba(0,0,0,.4);overflow:hidden}
.mk-etiket{box-sizing:border-box;padding:2mm 3mm;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;outline:1px dashed #ddd;font-family:system-ui,sans-serif}
.mk-etiket .ad{font-size:${olcu === '3x8' ? 9 : 7.5}pt;line-height:1.15;max-height:2.3em;overflow:hidden}
.mk-etiket .fiyat{font-weight:700;font-size:${olcu === '3x8' ? 13 : 10}pt}
.mk-etiket svg{width:100%;height:${olcu === '3x8' ? 12 : 9}mm;color:#000}
.mk-etiket .kod{font:${olcu === '3x8' ? 8 : 6.5}pt ui-monospace,monospace;text-align:center;letter-spacing:.05em}
@media screen and (max-width:640px){.mk-etiket-sayfa{zoom:.45}}
@media print{
  @page{size:A4;margin:0}
  html,body{background:#fff!important}
  body>*:not(.mk-etiket-kok){display:none!important}
  .mk-etiket-kok{position:static;padding:0;background:#fff;overflow:visible}
  .mk-etiket-kontrol{display:none!important}
  .mk-etiket-sayfa{box-shadow:none;margin:0;page-break-after:always;break-after:page}
  .mk-etiket{outline:none}
}`;
  return createPortal(
    <div className="mk-etiket-kok" role="dialog" aria-modal="true" aria-label={t('stokPos.etiket.baslik')} data-testid="stok-etiketler">
      <style>{stil}</style>
      <div className="mk-etiket-kontrol mx-auto mb-3 flex max-w-3xl flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-[#120b1f] p-3 text-sm text-white">
        <strong className="me-auto">{t('stokPos.etiket.baslik')}</strong>
        <label className="flex items-center gap-1.5">
          {t('stokPos.etiket.olcu')}
          <select className="h-8 rounded-md border border-white/10 bg-black/40 px-2" value={olcu} onChange={(e) => setOlcu(e.target.value as Olcu)} data-testid="stok-etiket-olcu">
            <option value="3x8">3 × 8 (70 × 37 mm)</option>
            <option value="4x10">4 × 10 (52,5 × 29,7 mm)</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" className="accent-purple-500" checked={fiyat} onChange={(e) => setFiyat(e.target.checked)} />
          {t('stokPos.etiket.fiyat')}
        </label>
        <Button size="sm" className="gap-1.5" onClick={() => window.print()} data-testid="stok-etiket-yazdir">
          <Printer className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.fis.yazdir')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onKapat} data-testid="stok-etiket-kapat">
          <X className="h-4 w-4" aria-hidden="true" />
          {t('stokPos.kapat')}
        </Button>
        <ul className="w-full space-y-1">
          {urunler.map((u) => (
            <li key={u.id} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate">{u.ad}</span>
              <input
                type="number"
                min={0}
                max={300}
                className="h-8 w-20 rounded-md border border-white/10 bg-black/40 px-2 text-center"
                value={adetler[u.id] ?? 0}
                onChange={(e) => setAdetler({ ...adetler, [u.id]: Math.max(0, Math.min(300, Number(e.target.value) || 0)) })}
                aria-label={t('stokPos.etiket.adet', { ad: u.ad })}
              />
            </li>
          ))}
        </ul>
        <p className="w-full text-xs text-muted-foreground">{t('stokPos.etiket.ipucu', { sayi: etiketler.length, sayfa: sayfalar.length })}</p>
      </div>
      {sayfalar.map((sayfa, i) => (
        <div key={i} className="mk-etiket-sayfa" data-testid="stok-etiket-sayfa">
          {sayfa.map((u, j) => (
            <div key={j} className="mk-etiket" data-testid="stok-etiket-oge">
              <div className="ad">{u.ad}</div>
              {fiyat && <div className="fiyat">{para(u.satis_fiyati, paraBirimi, dil)}</div>}
              <Barkod kod={u.barkod} />
              <div className="kod" dir="ltr">
                {u.barkod}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>,
    document.body
  );
}
