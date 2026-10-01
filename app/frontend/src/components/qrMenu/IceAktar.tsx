import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, Download, FileUp, Loader2, XCircle } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { DIS_DUGME, KART } from '@/components/qrMenu/ortak';
import { blobIndir, hataMetni, type IceAktarOnizleme, type Magaza, type MenuApi, type MenuMeta } from '@/lib/qrMenu';
import { paraYaz } from '@/lib/qrMenuOrtak';

/** Faz 4M — CSV ile toplu ürün içe aktarma: önizleme + hatalı satırlar → yalnız geçerliler eklenir. */

const ORNEK = 'kategori;ad;aciklama;fiyat;etiketler\nİçecekler;Ayran;Köpüklü, soğuk;25,00;vejetaryen\nTatlılar;Baklava;Fıstıklı, 4 dilim;180;yeni, çok satan\n';

export default function IceAktar({ api, meta, magaza, yazilabilir, onBitti }: { api: MenuApi; meta: MenuMeta; magaza: Magaza; yazilabilir: boolean; onBitti: () => void }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const girdi = useRef<HTMLInputElement>(null);
  const [onizleme, setOnizleme] = useState<IceAktarOnizleme | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const sec = async (dosya: File | undefined) => {
    if (!dosya) return;
    setMesgul(true);
    try {
      setOnizleme(await api.iceAktarOnizleme(magaza.id, dosya));
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
      if (girdi.current) girdi.current.value = '';
    }
  };

  const aktar = async () => {
    if (!onizleme) return;
    setMesgul(true);
    try {
      const y = await api.iceAktar(magaza.id, onizleme.satirlar.filter((s) => s.gecerli));
      toast.success(t('qrMenu.ice.bitti', { sayi: y.olusturulan, kategori: y.yeni_kategori }));
      if (y.hatalar.length) toast.error(t('qrMenu.ice.atlanan', { sayi: y.hatalar.length }));
      onBitti();
    } catch (e) {
      toast.error(hataMetni(t, e));
    } finally {
      setMesgul(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="menu-ice-aktar">
      <div className={`${KART} space-y-3 p-4 sm:p-6`}>
        <p className="text-sm text-muted-foreground">{t('qrMenu.ice.aciklama', { sayi: meta.csv_en_cok_satir })}</p>
        <pre className="overflow-x-auto rounded-lg bg-black/40 p-3 text-xs" dir="ltr">
          {ORNEK}
        </pre>
        <div className="flex flex-wrap gap-2">
          <input ref={girdi} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => void sec(e.target.files?.[0])} data-testid="menu-ice-dosya" />
          <Button onClick={() => girdi.current?.click()} disabled={!yazilabilir || mesgul} className="gap-1.5">
            {mesgul ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <FileUp className="h-4 w-4" aria-hidden="true" />}
            {t('qrMenu.ice.dosyaSec')}
          </Button>
          <Button variant="outline" className={DIS_DUGME} onClick={() => blobIndir(new Blob(['﻿' + ORNEK], { type: 'text/csv;charset=utf-8' }), 'menu-ornek.csv')}>
            <Download className="h-4 w-4" aria-hidden="true" />
            {t('qrMenu.ice.ornekIndir')}
          </Button>
        </div>
      </div>
      {onizleme && (
        <div className={`${KART} space-y-3 p-4 sm:p-6`} data-testid="menu-ice-onizleme">
          <p className="text-sm">
            {t('qrMenu.ice.ozet', { toplam: onizleme.toplam, gecerli: onizleme.gecerli, hatali: onizleme.hatali })}
            {onizleme.kalan_hak !== null && ` · ${t('qrMenu.ice.kalan', { sayi: onizleme.kalan_hak })}`}
          </p>
          {onizleme.yeni_kategoriler.length > 0 && (
            <p className="text-xs text-muted-foreground">{t('qrMenu.ice.yeniKategoriler', { liste: onizleme.yeni_kategoriler.join(', ') })}</p>
          )}
          <div className="max-h-[420px] overflow-auto rounded-xl border border-white/10">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[#120b1f] text-xs text-muted-foreground">
                <tr>
                  <th className="p-2 text-start font-normal">#</th>
                  <th className="p-2 text-start font-normal">{t('qrMenu.urun.kategori')}</th>
                  <th className="p-2 text-start font-normal">{t('qrMenu.urun.ad')}</th>
                  <th className="p-2 text-end font-normal">{t('qrMenu.urun.fiyat')}</th>
                  <th className="p-2 text-start font-normal">{t('qrMenu.ice.durum')}</th>
                </tr>
              </thead>
              <tbody>
                {onizleme.satirlar.map((s) => (
                  <tr key={s.satir} className={`border-t border-white/5 ${s.gecerli ? '' : 'bg-red-500/[0.06]'}`} data-ice-satir={s.satir} data-gecerli={s.gecerli}>
                    <td className="p-2 text-xs text-muted-foreground">{s.satir}</td>
                    <td className="p-2">{s.veri?.kategori ?? s.ham.kategori}</td>
                    <td className="p-2">{s.veri?.ad ?? s.ham.ad}</td>
                    <td className="p-2 text-end tabular-nums">{s.veri ? paraYaz(s.veri.fiyat, magaza.para_birimi, dil) : s.ham.fiyat}</td>
                    <td className="p-2 text-xs">
                      {s.gecerli ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-label={t('qrMenu.ice.gecerli')} />
                      ) : (
                        <span className="flex items-center gap-1 text-red-200">
                          <XCircle className="h-4 w-4 flex-none" aria-hidden="true" />
                          {t(`qrMenu.hata.${s.hata?.kod}`, { ...(s.hata || {}), defaultValue: t('qrMenu.hata.genel') })}
                          {s.hata?.alan ? ` (${s.hata.alan})` : ''}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button onClick={() => void aktar()} disabled={!yazilabilir || mesgul || onizleme.gecerli === 0} className="gap-1.5" data-testid="menu-ice-aktar-onay">
            {mesgul && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('qrMenu.ice.aktar', { sayi: onizleme.gecerli })}
          </Button>
        </div>
      )}
    </div>
  );
}
