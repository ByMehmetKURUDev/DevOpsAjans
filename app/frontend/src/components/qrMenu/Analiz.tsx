import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { KART, SECIM, sayiYaz } from '@/components/qrMenu/ortak';
import { hataMetni, type Analiz as AnalizVerisi, type Magaza, type MenuApi } from '@/lib/qrMenu';
import { paraYaz } from '@/lib/qrMenuOrtak';

/** Faz 4M — menü analizi: görüntülenme, tekil, en çok bakılan ürünler, sepet, sipariş. Botlar ayrı. */
export default function Analiz({ api, magaza }: { api: MenuApi; magaza: Magaza }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [gun, setGun] = useState(30);
  const [veri, setVeri] = useState<AnalizVerisi | null>(null);

  useEffect(() => {
    let iptal = false;
    setVeri(null);
    api
      .analiz(magaza.id, gun)
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch((e) => toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, magaza.id, gun, t]);

  if (!veri) {
    return (
      <div className="flex justify-center py-12 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
      </div>
    );
  }
  const enCok = Math.max(1, ...veri.gunluk.map((g) => g.goruntuleme));
  const kartlar: [string, string][] = [
    ['goruntuleme', sayiYaz(veri.goruntuleme, dil)],
    ['tekil', sayiYaz(veri.tekil, dil)],
    ['urun_goruntuleme', sayiYaz(veri.urun_goruntuleme, dil)],
    ['sepete_ekleme', sayiYaz(veri.sepete_ekleme, dil)],
    ['siparis', sayiYaz(veri.siparis, dil)],
    ['siparis_tutari', paraYaz(veri.siparis_tutari, veri.para_birimi, dil)],
  ];
  return (
    <div className="space-y-4" data-testid="menu-analiz">
      <div className={`${KART} flex flex-wrap items-center gap-3 p-4`}>
        <label className="flex items-center gap-2 text-sm">
          {t('qrMenu.analiz.donem')}
          <select className={`${SECIM} w-32`} value={gun} onChange={(e) => setGun(Number(e.target.value))}>
            {[7, 30, 90].map((g) => (
              <option key={g} value={g}>
                {t('qrMenu.analiz.gun', { sayi: g })}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-muted-foreground" data-testid="menu-analiz-bot">
          {t('qrMenu.analiz.bot', { sayi: veri.bot })}
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {kartlar.map(([k, v]) => (
          <div key={k} className={`${KART} p-4`} data-menu-istatistik={k}>
            <dt className="text-xs text-muted-foreground">{t(`qrMenu.analiz.${k}`)}</dt>
            <dd className="mt-1 text-xl font-bold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 text-sm font-semibold">{t('qrMenu.analiz.gunluk')}</h4>
        <div className="flex h-36 items-end gap-[2px]" role="img" aria-label={t('qrMenu.analiz.gunluk')} data-testid="menu-analiz-grafik">
          {veri.gunluk.map((g) => (
            <div key={g.gun} className="flex h-full flex-1 flex-col justify-end" title={`${g.gun}: ${g.goruntuleme} / ${g.tekil}`}>
              <div className="rounded-t bg-purple-400/80" style={{ height: `${(g.goruntuleme / enCok) * 100}%`, minHeight: g.goruntuleme ? 2 : 0 }} />
            </div>
          ))}
        </div>
      </div>
      <div className={`${KART} p-4 sm:p-6`}>
        <h4 className="mb-3 text-sm font-semibold">{t('qrMenu.analiz.enCok')}</h4>
        {veri.en_cok_bakilan.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('qrMenu.analiz.veriYok')}</p>
        ) : (
          <table className="w-full text-sm" data-testid="menu-analiz-urunler">
            <thead>
              <tr className="text-start text-xs text-muted-foreground">
                <th className="py-1 text-start font-normal">{t('qrMenu.analiz.urun')}</th>
                <th className="py-1 text-end font-normal">{t('qrMenu.analiz.urun_goruntuleme')}</th>
                <th className="py-1 text-end font-normal">{t('qrMenu.analiz.sepete_ekleme')}</th>
              </tr>
            </thead>
            <tbody>
              {veri.en_cok_bakilan.map((u) => (
                <tr key={u.urun_id} className="border-t border-white/5">
                  <td className="py-1.5">{u.ad}</td>
                  <td className="py-1.5 text-end tabular-nums">{sayiYaz(u.goruntuleme, dil)}</td>
                  <td className="py-1.5 text-end tabular-nums">{sayiYaz(u.sepet, dil)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
