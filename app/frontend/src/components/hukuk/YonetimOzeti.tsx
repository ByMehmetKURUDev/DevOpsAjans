import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShieldCheck } from 'lucide-react';

import { KART, Not, Rozet, Yukleniyor } from '@/components/hukuk/ortak';
import { boyutYaz, hataMetni, hukukYonetimApi, type HesapMetasi } from '@/lib/hukuk';

/**
 * Faz 6H — yöneticinin destek görünümü: hesap başına YALNIZ sayılar (müvekkil, dosya, yaklaşan süre, depolama,
 * portal bağlantısı). Dosya içeriği, not, belge, müvekkil adı uçtan zaten dönmüyor.
 */
export default function YonetimOzeti() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [veri, setVeri] = useState<{ hesaplar: HesapMetasi[]; toplam: Record<string, number> } | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    hukukYonetimApi
      .ozet()
      .then(setVeri)
      .catch((e) => setHata(hataMetni(t, e)));
  }, [t]);

  const sayi = (n: number) => new Intl.NumberFormat(dil).format(n || 0);

  return (
    <div className="space-y-4" data-testid="hukuk-yonetim">
      <Not testid="hukuk-yonetim-gizlilik">
        <ShieldCheck className="me-1 inline h-3.5 w-3.5" aria-hidden="true" />
        {t('hukuk.yonetim.gizlilik')}
      </Not>
      <div className={`${KART} overflow-x-auto p-4 sm:p-6`}>
        <h3 className="mb-3 text-base font-semibold">{t('hukuk.yonetim.baslik')}</h3>
        {hata && (
          <p className="text-sm text-red-300" role="alert">
            {hata}
          </p>
        )}
        {!veri && !hata ? (
          <Yukleniyor />
        ) : veri && veri.hesaplar.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground" data-testid="hukuk-yonetim-bos">
            {t('hukuk.yonetim.bos')}
          </p>
        ) : veri ? (
          <table className="w-full min-w-[720px] text-sm" data-testid="hukuk-yonetim-tablo">
            <thead>
              <tr className="border-b border-white/10 text-start text-xs text-muted-foreground">
                <th className="py-2 text-start font-medium">{t('hukuk.yonetim.hesap')}</th>
                <th className="py-2 text-start font-medium">{t('hukuk.yonetim.modul')}</th>
                <th className="py-2 text-end font-medium">{t('hukuk.yonetim.muvekkil')}</th>
                <th className="py-2 text-end font-medium">{t('hukuk.yonetim.dosya')}</th>
                <th className="py-2 text-end font-medium">{t('hukuk.yonetim.yaklasan')}</th>
                <th className="py-2 text-end font-medium">{t('hukuk.yonetim.depolama')}</th>
                <th className="py-2 text-end font-medium">{t('hukuk.yonetim.portal')}</th>
              </tr>
            </thead>
            <tbody>
              {veri.hesaplar.map((h) => (
                <tr key={h.hesap_email} className="border-b border-white/5" data-hesap={h.hesap_email}>
                  <td className="py-2 font-mono text-xs" dir="ltr">
                    {h.hesap_email}
                  </td>
                  <td className="py-2">
                    <Rozet renk={h.modul_acik ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-200' : undefined}>
                      {h.modul_acik ? t('hukuk.yonetim.acik') : t('hukuk.yonetim.kapali')}
                    </Rozet>
                  </td>
                  <td className="py-2 text-end">{sayi(h.muvekkil_sayisi)}</td>
                  <td className="py-2 text-end">
                    {sayi(h.dosya_sayisi)} <span className="text-xs text-muted-foreground">({sayi(h.acik_dosya)}/{sayi(h.kapanan_dosya)})</span>
                  </td>
                  <td className="py-2 text-end">{sayi(h.yaklasan_sure)}</td>
                  <td className="py-2 text-end">{boyutYaz(h.depolama_bayt)}</td>
                  <td className="py-2 text-end">{sayi(h.portal_bagli_muvekkil)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="text-xs text-muted-foreground">
                <td className="pt-2" colSpan={2}>
                  {t('hukuk.yonetim.toplam')}
                </td>
                <td className="pt-2 text-end">{sayi(veri.toplam.muvekkil_sayisi)}</td>
                <td className="pt-2 text-end">{sayi(veri.toplam.dosya_sayisi)}</td>
                <td className="pt-2 text-end">{sayi(veri.toplam.yaklasan_sure)}</td>
                <td className="pt-2 text-end">{boyutYaz(veri.toplam.depolama_bayt || 0)}</td>
                <td className="pt-2 text-end">{sayi(veri.toplam.portal_bagli_muvekkil)}</td>
              </tr>
            </tfoot>
          </table>
        ) : null}
      </div>
    </div>
  );
}
