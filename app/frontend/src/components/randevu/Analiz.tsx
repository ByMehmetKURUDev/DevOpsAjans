import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { KART, SECIM, Yukleniyor, sayiYaz } from '@/components/randevu/ortak';
import { hataMetni, type Analiz as AnalizVerisi, type RandevuApi, type Sayfa } from '@/lib/randevu';
import { gunAdiYaz } from '@/lib/randevuOrtak';

/** Faz 5R — analiz: sayfa görüntüleme → rezervasyon dönüşümü (bot ve ham IP yok). */

export default function Analiz({ api, sayfa }: { api: RandevuApi; sayfa: Sayfa }) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [gun, setGun] = useState(30);
  const [veri, setVeri] = useState<AnalizVerisi | null>(null);

  useEffect(() => {
    let iptal = false;
    setVeri(null);
    api
      .analiz(sayfa.id, gun)
      .then((v) => {
        if (!iptal) setVeri(v);
      })
      .catch((e) => toast.error(hataMetni(t, e)));
    return () => {
      iptal = true;
    };
  }, [api, sayfa.id, gun, t]);

  const kartlar = veri
    ? [
        { anahtar: 'goruntuleme', deger: sayiYaz(veri.goruntuleme, dil) },
        { anahtar: 'tekil', deger: sayiYaz(veri.tekil, dil) },
        { anahtar: 'rezervasyon', deger: sayiYaz(veri.rezervasyon, dil) },
        { anahtar: 'donusum', deger: veri.donusum === null ? '—' : `%${sayiYaz(veri.donusum, dil)}` },
        { anahtar: 'iptal', deger: sayiYaz(veri.iptal, dil) },
        { anahtar: 'gelmedi', deger: sayiYaz(veri.katilim.gelmedi, dil) },
      ]
    : [];
  const enCok = veri ? Math.max(1, ...veri.gunluk.map((g) => g.goruntuleme)) : 1;

  return (
    <div className={`${KART} p-4 sm:p-6`} data-testid="randevu-analiz">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold">{t('randevu.analiz.baslik')}</h3>
        <select className={`${SECIM} w-auto`} value={gun} onChange={(e) => setGun(Number(e.target.value))} aria-label={t('randevu.analiz.donem')}>
          {[7, 30, 90, 365].map((g) => (
            <option key={g} value={g}>
              {t('randevu.analiz.sonGun', { sayi: g })}
            </option>
          ))}
        </select>
      </div>
      {!veri ? (
        <Yukleniyor />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {kartlar.map((k) => (
              <div key={k.anahtar} className="rounded-xl border border-white/10 bg-black/20 p-3" data-analiz={k.anahtar}>
                <dt className="text-xs text-muted-foreground">{t(`randevu.analiz.${k.anahtar}`)}</dt>
                <dd className="mt-1 text-2xl font-semibold">{k.deger}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-muted-foreground">{t('randevu.analiz.ipucu')}</p>
          {veri.gunluk.length > 0 && (
            <div className="mt-5">
              <h4 className="mb-2 text-sm font-medium">{t('randevu.analiz.gunluk')}</h4>
              <ul className="space-y-1">
                {veri.gunluk.slice(-31).map((g) => (
                  <li key={g.gun} className="grid grid-cols-[7rem_minmax(0,1fr)_3rem] items-center gap-2 text-xs">
                    <span className="text-muted-foreground">{gunAdiYaz(g.gun, dil, { day: 'numeric', month: 'short' })}</span>
                    <span className="relative h-3 rounded bg-white/5" aria-hidden="true">
                      <span className="absolute inset-y-0 start-0 rounded bg-purple-500/60" style={{ width: `${(g.goruntuleme / enCok) * 100}%` }} />
                    </span>
                    <span className="text-end tabular-nums">
                      {g.goruntuleme} / {g.rezervasyon}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[11px] text-muted-foreground">{t('randevu.analiz.gunlukIpucu')}</p>
            </div>
          )}
          {veri.turler.length > 0 && (
            <div className="mt-5 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground">
                    <th className="py-1 text-start font-normal">{t('randevu.analiz.tur')}</th>
                    <th className="py-1 text-end font-normal">{t('randevu.analiz.goruntuleme')}</th>
                    <th className="py-1 text-end font-normal">{t('randevu.analiz.rezervasyon')}</th>
                  </tr>
                </thead>
                <tbody>
                  {veri.turler.map((x) => (
                    <tr key={x.id} className="border-t border-white/5">
                      <td className="py-1.5">
                        <span className="me-2 inline-block h-2 w-2 rounded-full" style={{ background: x.renk }} aria-hidden="true" />
                        {x.ad}
                      </td>
                      <td className="py-1.5 text-end tabular-nums">{sayiYaz(x.goruntuleme, dil)}</td>
                      <td className="py-1.5 text-end tabular-nums">{sayiYaz(x.rezervasyon, dil)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
