import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { KART, Rozet, Yukleniyor } from '@/components/randevu/ortak';
import { hataMetni, type Etkinlik, type EtkinlikApi, type Satis as SatisVerisi } from '@/lib/etkinlik';
import { paraYaz } from '@/lib/etkinlikOrtak';

/**
 * Faz 6E — satış raporu: gelir (onaylı siparişler), indirim, ödeme bekleyen, bilet türü kırılımı,
 * iade durumu ve indirim kodu kullanımı. Ücretsiz etkinlikte yalnız adetler anlamlı.
 */
export default function Satis({ api, etkinlik }: { api: EtkinlikApi; etkinlik: Etkinlik }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [v, setV] = useState<SatisVerisi | null>(null);

  useEffect(() => {
    let iptal = false;
    api
      .satis(etkinlik.id)
      .then((x) => !iptal && setV(x))
      .catch((e) => {
        toast.error(hataMetni(t, e));
      });
    return () => {
      iptal = true;
    };
  }, [api, etkinlik.id, t]);

  if (!v) return <Yukleniyor />;
  const ucretli = v.turler.some((x) => x.fiyat > 0);
  const para = (k: number, p = v.para_birimi) => paraYaz(k, p, dil);

  return (
    <div className="space-y-4" data-testid="etkinlik-satis">
      {!ucretli && <p className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm text-muted-foreground">{t(etkinlik.ajans ? 'etkinlik.satis.ucretsiz' : 'etkinlik.satis.ucretsizMusteri')}</p>}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ['gelir', para(v.gelir)],
          ['indirim', para(v.indirim)],
          ['bekleyen', `${v.bekleyen_odeme.sayi || 0} · ${para(v.bekleyen_odeme.toplam || 0)}`],
          ['siparis', String(v.siparisler.onayli?.sayi || 0)],
        ].map(([ad, deger]) => (
          <div key={ad} className={`${KART} p-3`}>
            <div className="text-xs text-muted-foreground">{t(`etkinlik.satis.${ad}`)}</div>
            <div className="text-lg font-bold tabular-nums" data-testid={`etkinlik-satis-${ad}`}>
              {deger}
            </div>
          </div>
        ))}
      </div>

      <div className={`${KART} overflow-x-auto p-4 sm:p-6`}>
        <h3 className="mb-2 font-semibold">{t('etkinlik.satis.turler')}</h3>
        <table className="w-full min-w-[32rem] text-sm">
          <thead className="text-start text-xs text-muted-foreground">
            <tr>
              <th className="py-1 text-start font-medium">{t('etkinlik.bilet.ad')}</th>
              <th className="py-1 text-end font-medium">{t('etkinlik.bilet.fiyat')}</th>
              <th className="py-1 text-end font-medium">{t('etkinlik.biletDurumu.gecerli')}</th>
              <th className="py-1 text-end font-medium">{t('etkinlik.biletDurumu.odeme_bekliyor')}</th>
              <th className="py-1 text-end font-medium">{t('etkinlik.biletDurumu.iptal')}</th>
              <th className="py-1 text-end font-medium">{t('etkinlik.satis.brut')}</th>
            </tr>
          </thead>
          <tbody>
            {v.turler.map((x) => (
              <tr key={x.id} className="border-t border-white/5">
                <td className="py-1.5">{x.ad}</td>
                <td className="py-1.5 text-end tabular-nums">{x.fiyat ? para(x.fiyat, x.para_birimi) : t('etkinlik.bilet.ucretsiz')}</td>
                <td className="py-1.5 text-end tabular-nums">{x.gecerli}</td>
                <td className="py-1.5 text-end tabular-nums">{x.bekleyen}</td>
                <td className="py-1.5 text-end tabular-nums">{x.iptal}</td>
                <td className="py-1.5 text-end tabular-nums">{para(x.brut, x.para_birimi)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className={`${KART} p-4 sm:p-6`}>
          <h3 className="mb-2 font-semibold">{t('etkinlik.satis.siparisler')}</h3>
          <ul className="space-y-1 text-sm">
            {Object.entries(v.siparisler).map(([d, x]) => (
              <li key={d} className="flex justify-between gap-2">
                <span>{t(`etkinlik.siparisDurumu.${d}`, { defaultValue: d })}</span>
                <span className="tabular-nums text-muted-foreground">
                  {x.sayi} · {para(x.toplam)}
                </span>
              </li>
            ))}
            {Object.keys(v.siparisler).length === 0 && <li className="text-muted-foreground">{t('etkinlik.satis.bos')}</li>}
          </ul>
          {Object.keys(v.iade).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(v.iade).map(([d, n]) => (
                <Rozet key={d}>
                  {t(`etkinlik.iade.${d}`)}: {n}
                </Rozet>
              ))}
            </div>
          )}
        </div>
        <div className={`${KART} p-4 sm:p-6`}>
          <h3 className="mb-2 font-semibold">{t('etkinlik.indirim.baslik')}</h3>
          {v.indirim_kodlari.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('etkinlik.indirim.bos')}</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {v.indirim_kodlari.map((x) => (
                <li key={x.kod} className="flex justify-between gap-2">
                  <code>{x.kod}</code>
                  <span className="tabular-nums text-muted-foreground">
                    {x.kullanilan}
                    {x.kullanim_siniri ? ` / ${x.kullanim_siniri}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
