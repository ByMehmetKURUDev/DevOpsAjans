import { useCallback, useEffect, useState } from 'react';
import { Laptop, Loader2, LogOut, RefreshCw, ShieldCheck, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { goreliZaman, tamZaman } from '@/lib/denetim';
import { digerleriniKapat, GuvenlikHatasi, oturumlarim, oturumumuKapat, type Oturum } from '@/lib/guvenlik';
import { oturumIziniTemizle } from '@/lib/sdkClient';

/**
 * Müşteri paneli › Profil › Oturumlarım.
 *
 * Hesabın açık olduğu cihazlar ("Bu cihaz" işaretli). Tanınmayan bir oturum
 * tek tıkla kapatılır; "Diğer tüm oturumları kapat" bu cihaz dışındaki
 * hepsini kapatır. Bu cihazın oturumu kapatılırsa çıkış yapılmış olur.
 * Liste sunucuda jetondaki e-postaya göre süzülüyor.
 */
export default function Oturumlarim() {
  const { t, i18n } = useTranslation();
  const dil = i18n.language;
  const [satirlar, setSatirlar] = useState<Oturum[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [calisan, setCalisan] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      setSatirlar(await oturumlarim());
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const hataMetni = (h: unknown) =>
    t(`guvenlik.hataKod.${h instanceof GuvenlikHatasi ? h.kod : 'genel'}`, {
      defaultValue: t('guvenlik.hataKod.genel'),
    });

  const kapat = async (s: Oturum) => {
    const onay = s.bu_cihaz
      ? t('guvenlik.kisi.buCihazOnay')
      : t('guvenlik.kapatOnay', { cihaz: s.cihaz || t('guvenlik.bilinmeyenCihaz'), eposta: '' });
    if (!window.confirm(onay)) return;
    setCalisan(`kapat-${s.id}`);
    try {
      await oturumumuKapat(s.id);
      if (s.bu_cihaz) {
        oturumIziniTemizle();
        window.location.href = '/';
        return;
      }
      toast.success(t('guvenlik.kapatildi'));
      await yukle();
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setCalisan(null);
    }
  };

  const digerleri = async () => {
    if (!window.confirm(t('guvenlik.kisi.digerleriOnay'))) return;
    setCalisan('digerleri');
    try {
      const g = await digerleriniKapat();
      toast.success(
        g.kapatilan > 0 ? t('guvenlik.kisi.digerleriKapatildi', { sayi: g.kapatilan }) : t('guvenlik.kisi.digerleriYok')
      );
      await yukle();
    } catch (h) {
      toast.error(hataMetni(h));
    } finally {
      setCalisan(null);
    }
  };

  const buCihazVar = satirlar.some((s) => s.bu_cihaz);
  const baskaVar = satirlar.some((s) => !s.bu_cihaz);

  return (
    <section
      className="cam-kart max-w-xl rounded-2xl border border-white/10 bg-white/[0.03] p-6"
      aria-labelledby="oturumlarim-baslik"
      data-testid="oturumlarim"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 id="oturumlarim-baslik" className="flex items-center gap-2 text-lg font-semibold">
            <ShieldCheck className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {t('guvenlik.kisi.baslik')}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('guvenlik.kisi.aciklama')}</p>
        </div>
        <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('guvenlik.yenile')}>
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
        </Button>
      </div>

      {yukleniyor && satirlar.length === 0 ? (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : hata ? (
        <p className="py-4 text-sm text-red-300">{t('guvenlik.hata')}</p>
      ) : (
        <>
          {satirlar.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">{t('guvenlik.kisi.bos')}</p>
          ) : (
            <ul className="space-y-2">
              {satirlar.map((s) => (
                <li
                  key={s.id}
                  className="flex items-start gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3"
                  data-testid={`oturumum-${s.id}`}
                >
                  <Laptop className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm">
                      {s.cihaz || t('guvenlik.bilinmeyenCihaz')}
                      {s.bu_cihaz && (
                        <span
                          className="rounded-full border border-purple-400/30 bg-purple-500/10 px-2 py-0.5 text-[11px] text-purple-200"
                          data-testid="bu-cihaz-rozeti"
                        >
                          {t('guvenlik.buCihaz')}
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      <span title={tamZaman(s.son_gorulme, dil)}>
                        {t('guvenlik.kisi.sonEtkinlik', { zaman: goreliZaman(s.son_gorulme, dil) })}
                      </span>
                      {' · '}
                      <span title={tamZaman(s.olusturma, dil)}>
                        {t('guvenlik.kisi.acilis', { zaman: goreliZaman(s.olusturma, dil) })}
                      </span>
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={calisan !== null}
                    onClick={() => void kapat(s)}
                    data-testid={`oturumum-kapat-${s.id}`}
                  >
                    {calisan === `kapat-${s.id}` ? (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : s.bu_cihaz ? (
                      <LogOut className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                    ) : (
                      <XCircle className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                    )}
                    {s.bu_cihaz ? t('guvenlik.kisi.cikisYap') : t('guvenlik.kapat')}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {!buCihazVar && <p className="mt-3 text-[11px] text-muted-foreground">{t('guvenlik.kisi.eskiOturum')}</p>}
          <Button
            variant="outline"
            className="mt-4 w-full border-red-400/30 text-red-200 hover:bg-red-500/10"
            disabled={calisan !== null || !baskaVar}
            onClick={() => void digerleri()}
            data-testid="digerlerini-kapat"
          >
            {calisan === 'digerleri' ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
            )}
            {t('guvenlik.kisi.digerleri')}
          </Button>
        </>
      )}
    </section>
  );
}
