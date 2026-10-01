import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { asamaAdi, hataMetni, ozetGetir, renk, toplamlarGoster, type Asama, type Ozet } from '@/lib/crm';
import { Bekle } from './ortak';

/**
 * Huni özeti (kütüphanesiz): sayı kartları, huni dönüşüm çubukları, kaynak
 * başına aday/kazanma oranı ve ortalama aşama süresi. Grafik kütüphanesi
 * yok — çubuklar yüzde genişlikli div; ana paket ve CRM parçası küçük kalıyor.
 */
export default function CrmOzeti({ asamalar }: { asamalar: Asama[] }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [ozet, setOzet] = useState<Ozet | null>(null);

  useEffect(() => {
    let iptal = false;
    ozetGetir()
      .then((o) => !iptal && setOzet(o))
      .catch((e) => toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [t]);

  if (!ozet) return <Bekle />;
  const harita = new Map(asamalar.map((a) => [a.anahtar, a]));
  const enCok = Math.max(1, ...ozet.huni.map((h) => h.ulasan));
  const yuzde = (x: number | null | undefined) =>
    x === null || x === undefined ? '—' : new Intl.NumberFormat(dil, { style: 'percent', maximumFractionDigits: 0 }).format(x);
  const sayi = (x: number) => new Intl.NumberFormat(dil, { maximumFractionDigits: 1 }).format(x);

  const kartlar: { ad: string; deger: string; ek?: string }[] = [
    { ad: t('crm.ozet.toplam'), deger: sayi(ozet.toplam) },
    { ad: t('crm.ozet.acik'), deger: sayi(ozet.acik), ek: toplamlarGoster(ozet.acik_deger, dil) },
    { ad: t('crm.ozet.buAy'), deger: sayi(ozet.bu_ay.kazanilan_sayi), ek: toplamlarGoster(ozet.bu_ay.deger, dil) || '—' },
    { ad: t('crm.ozet.kazanilan'), deger: sayi(ozet.kazanilan) },
    { ad: t('crm.ozet.kaybedilen'), deger: sayi(ozet.kaybedilen) },
    { ad: t('crm.ozet.geciken'), deger: sayi(ozet.geciken) },
  ];

  return (
    <div className="space-y-5" data-testid="crm-ozet">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {kartlar.map((k) => (
          <div key={k.ad} className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs text-muted-foreground">{k.ad}</p>
            <p className="mt-1 text-2xl font-bold tabular-nums">{k.deger}</p>
            {k.ek ? <p className="mt-0.5 truncate text-xs text-muted-foreground">{k.ek}</p> : null}
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" aria-labelledby="crm-huni-baslik">
          <h3 id="crm-huni-baslik" className="mb-1 text-sm font-semibold">
            {t('crm.ozet.huni')}
          </h3>
          <p className="mb-3 text-xs text-muted-foreground">{t('crm.ozet.huniAciklama')}</p>
          <ul className="space-y-2.5">
            {ozet.huni.map((h) => {
              const a = harita.get(h.anahtar);
              return (
                <li key={h.anahtar}>
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate">{asamaAdi(a, dil)}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {t('crm.ozet.ulasan', { sayi: h.ulasan })}
                      {h.donusum !== null ? ` · ${t('crm.ozet.sonrakine', { oran: yuzde(h.donusum) })}` : ''}
                    </span>
                  </div>
                  <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-white/5" aria-hidden="true">
                    <div className={`h-full rounded-full ${renk(a?.renk).nokta}`} style={{ width: `${(h.ulasan / enCok) * 100}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" aria-labelledby="crm-kaynak-baslik">
          <h3 id="crm-kaynak-baslik" className="mb-3 text-sm font-semibold">
            {t('crm.ozet.kaynaklar')}
          </h3>
          {ozet.kaynaklar.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('crm.bos')}</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="pb-1 text-start font-medium">{t('crm.alan.kaynak')}</th>
                  <th className="pb-1 text-end font-medium">{t('crm.ozet.aday')}</th>
                  <th className="pb-1 text-end font-medium">{t('crm.ozet.kazanilan')}</th>
                  <th className="w-1/3 pb-1 text-end font-medium">{t('crm.ozet.kazanmaOrani')}</th>
                </tr>
              </thead>
              <tbody>
                {ozet.kaynaklar.map((k) => (
                  <tr key={k.kaynak} className="border-t border-white/5">
                    <td className="py-1.5">{t(`crm.kaynak.${k.kaynak}`)}</td>
                    <td className="py-1.5 text-end tabular-nums">{k.sayi}</td>
                    <td className="py-1.5 text-end tabular-nums">{k.kazanilan}</td>
                    <td className="py-1.5">
                      <div className="flex items-center justify-end gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/5" aria-hidden="true">
                          <div className="h-full bg-emerald-400" style={{ width: `${k.kazanma_orani * 100}%` }} />
                        </div>
                        <span className="w-10 text-end tabular-nums">{yuzde(k.kazanma_orani)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-4" aria-labelledby="crm-sure-baslik">
        <h3 id="crm-sure-baslik" className="mb-3 text-sm font-semibold">
          {t('crm.ozet.asamaSuresi')}
        </h3>
        {ozet.asama_sureleri.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('crm.ozet.sureYok')}</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {ozet.asama_sureleri.map((s) => (
              <li key={s.anahtar} className="rounded-xl border border-white/10 p-3 text-xs">
                <p className="text-muted-foreground">{asamaAdi(harita.get(s.anahtar), dil)}</p>
                <p className="mt-0.5 text-lg font-semibold tabular-nums">{t('crm.ozet.gun', { sayi: sayi(s.ortalama_gun) })}</p>
                <p className="text-[11px] text-muted-foreground">{t('crm.ozet.ornek', { sayi: s.ornek })}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
