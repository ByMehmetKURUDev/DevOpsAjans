import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Loader2, RefreshCcw, Rss, X } from 'lucide-react';

import { AbonelikTarifi, AdresKutusu, DUGME_IKINCIL, KART, Rozet, Zaman } from '@/components/toplantilar/ortak';
import { abonelikIptal, abonelikler, abonelikUret, hataKodu, type Abonelik } from '@/lib/toplantilar';

type Satir = { ad: string | null; email: string; tur: string; ben: boolean } & Abonelik;

/** Faz 6T — ekip üyelerinin (ve yöneticinin kendi) gizli takvim akışları: üret / yeniden üret / iptal. */
export default function Abonelikler() {
  const { t } = useTranslation();
  const [liste, setListe] = useState<Satir[] | null>(null);
  const [adresler, setAdresler] = useState<Record<string, string>>({});
  const [calisan, setCalisan] = useState<string | null>(null);

  const yukle = useCallback(() => {
    abonelikler()
      .then((g) => setListe(g.items))
      .catch(() => setListe([]));
  }, []);

  useEffect(() => {
    yukle();
  }, [yukle]);

  async function uret(e: string) {
    setCalisan(e);
    try {
      const g = await abonelikUret(e);
      if (g.adres) setAdresler((x) => ({ ...x, [e]: g.adres as string }));
      yukle();
    } catch (h) {
      toast.error(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') }));
    } finally {
      setCalisan(null);
    }
  }

  async function iptal(e: string) {
    setCalisan(e);
    try {
      await abonelikIptal(e);
      setAdresler((x) => {
        const y = { ...x };
        delete y[e];
        return y;
      });
      toast.success(t('toplantilar.abonelik.iptalEdildi'));
      yukle();
    } catch (h) {
      toast.error(t(`toplantilar.hata.${hataKodu(h)}`, { defaultValue: t('toplantilar.hata.genel') }));
    } finally {
      setCalisan(null);
    }
  }

  return (
    <section className={`${KART} p-4 sm:p-6`} data-testid="toplanti-abonelikleri">
      <h3 className="flex items-center gap-2 font-semibold">
        <Rss className="h-4 w-4 text-purple-300" aria-hidden="true" />
        {t('toplantilar.abonelik.baslik')}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">{t('toplantilar.abonelik.aciklamaYonetici')}</p>
      <AbonelikTarifi />
      {!liste ? (
        <div className="flex items-center justify-center py-10 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : (
        <ul className="mt-4 divide-y divide-white/5">
          {liste.map((k) => (
            <li key={k.email} className="py-3 text-sm" data-abone={k.email}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="break-all font-medium">
                    {k.ben ? t('toplantilar.abonelik.ben') : k.ad || k.email}
                    <span className="ms-2 text-xs font-normal text-muted-foreground" dir="ltr">{k.email}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {k.var ? (
                      <>
                        {t('toplantilar.abonelik.sonErisim')}: {k.son_erisim_at ? <Zaman iso={k.son_erisim_at} /> : t('toplantilar.abonelik.hic')}
                      </>
                    ) : (
                      t('toplantilar.abonelik.yok')
                    )}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {k.var && <Rozet tur="katilacak">{t('toplantilar.abonelik.var')}</Rozet>}
                  <button type="button" className={DUGME_IKINCIL} disabled={calisan === k.email} onClick={() => void uret(k.email)} data-abonelik-uret={k.email}>
                    {calisan === k.email ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCcw className="h-4 w-4" aria-hidden="true" />}
                    {k.var ? t('toplantilar.abonelik.yenidenUret') : t('toplantilar.abonelik.uret')}
                  </button>
                  {k.var && (
                    <button type="button" className={DUGME_IKINCIL} disabled={calisan === k.email} onClick={() => void iptal(k.email)}>
                      <X className="h-4 w-4" aria-hidden="true" />
                      {t('toplantilar.abonelik.iptal')}
                    </button>
                  )}
                </div>
              </div>
              {adresler[k.email] && <AdresKutusu adres={adresler[k.email]} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
