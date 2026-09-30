import { useCallback, useEffect, useState } from 'react';
import { BellRing, CheckCircle2, Grid3X3, Loader2, Lock, RefreshCw, Save, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import BildirimTercihleri, { Anahtar } from '@/components/BildirimTercihleri';
import { Button } from '@/components/ui/button';
import { matrisiGetir, matrisiKaydet, type Kanal, type Matris, type MatrisYaniti, type Rol } from '@/lib/bildirim';

/**
 * Yönetici › Bildirimler › olay × kanal matrisi, push durumu ve yöneticinin
 * kendi tercihleri.
 *
 * Matris alıcı rolüne göre iki tablo: yöneticiye giden ve müşteriye giden
 * bildirimler. Burada kapatılan hücreyi kişi kendi tercihinde açamaz; panel
 * içi (inapp) kapatılamaz. Kanalın kendisinin açık/kapalı olması (ana
 * anahtar) ve kimlik bilgileri ayrı: sütun başında durum olarak görünüyor.
 */

const ROLLER: Rol[] = ['admin', 'client'];

export default function BildirimMatrisi() {
  const { t } = useTranslation();
  const [veri, setVeri] = useState<MatrisYaniti | null>(null);
  const [taslak, setTaslak] = useState<Matris | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [kaydediliyor, setKaydediliyor] = useState(false);
  // Matris kaydedilince aşağıdaki kendi tercihlerim yeni izinlerle yeniden yüklensin.
  const [surum, setSurum] = useState(0);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      const v = await matrisiGetir();
      setVeri(v);
      setTaslak(JSON.parse(JSON.stringify(v.matris)) as Matris);
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const degistir = (rol: Rol, olay: string, kanal: Kanal, deger: boolean) =>
    setTaslak((eski) =>
      eski ? { ...eski, [rol]: { ...eski[rol], [olay]: { ...eski[rol][olay], [kanal]: deger } } } : eski
    );

  const kaydet = async () => {
    if (!taslak) return;
    setKaydediliyor(true);
    try {
      const v = await matrisiKaydet(taslak);
      setVeri(v);
      setTaslak(JSON.parse(JSON.stringify(v.matris)) as Matris);
      setSurum((n) => n + 1);
      toast.success(t('bildirim.matris.kaydedildi'));
    } catch {
      toast.error(t('bildirim.matris.kaydedilemedi'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const push = veri?.push;

  return (
    <div className="space-y-8" data-testid="bildirim-matrisi">
      {/* Push durumu */}
      <section
        className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6"
        data-testid="bildirim-push-karti"
      >
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <BellRing className="h-5 w-5 text-purple-400" aria-hidden="true" />
          {t('bildirim.pushDurum.baslik')}
        </h3>
        {!push ? (
          <div className="py-3 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-start gap-4">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs ${
                push.yapilandirildi ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'
              }`}
            >
              {push.yapilandirildi ? (
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {push.yapilandirildi ? t('bildirim.pushDurum.hazir') : t('bildirim.pushDurum.yokKisa')}
            </span>
            {push.yapilandirildi && (
              <span className="text-sm text-muted-foreground" data-testid="bildirim-push-sayac">
                {t('bildirim.pushDurum.abonelik', { sayi: push.abonelik_sayisi })} ·{' '}
                {t('bildirim.pushDurum.kisi', { sayi: push.kisi_sayisi ?? 0 })}
              </span>
            )}
            {!push.yapilandirildi && (
              <p className="w-full text-sm text-muted-foreground" data-testid="bildirim-push-karti-aciklama">
                {t('bildirim.pushDurum.yok')}{' '}
                <code className="rounded bg-purple-500/15 px-1.5 py-0.5 text-xs text-purple-200">
                  python scripts/vapid_uret.py vapid.env
                </code>
              </p>
            )}
          </div>
        )}
      </section>

      {/* Matris */}
      <section className="cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="mb-1 flex items-start justify-between gap-3">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Grid3X3 className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {t('bildirim.matris.baslik')}
          </h3>
          <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('bildirim.yenile')}>
            <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
          </Button>
        </div>
        <p className="mb-5 text-sm text-muted-foreground">{t('bildirim.matris.aciklama')}</p>

        {yukleniyor && !veri ? (
          <div className="flex justify-center py-6 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          </div>
        ) : hata || !veri || !taslak ? (
          <p className="py-4 text-sm text-red-300">{t('bildirim.matris.hata')}</p>
        ) : (
          <div className="space-y-6">
            <div className="flex flex-wrap gap-2 text-xs" aria-label={t('bildirim.matris.kanalDurumu')}>
              {veri.kanallar.map((k) => {
                const d = veri.kanal_durumu[k];
                return (
                  <span
                    key={k}
                    className={`rounded-full px-2.5 py-1 ${
                      d === 'hazir' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-white/10 text-muted-foreground'
                    }`}
                  >
                    {t(`bildirim.kanal.${k}`)}: {t(`bildirim.durum.${d}`)}
                  </span>
                );
              })}
            </div>

            {ROLLER.map((rol) => {
              const olaylar = veri.olaylar.filter((o) => o.roller.includes(rol));
              return (
                <div key={rol}>
                  <h4 className="mb-2 text-sm font-semibold">
                    {rol === 'admin' ? t('bildirim.matris.yonetici') : t('bildirim.matris.musteri')}
                  </h4>
                  <div className="overflow-x-auto">
                    <table
                      className="w-full min-w-[32rem] border-collapse text-sm"
                      data-testid={`bildirim-matris-${rol}`}
                    >
                      <thead>
                        <tr className="border-b border-white/10 text-xs text-muted-foreground">
                          <th scope="col" className="py-2 pe-3 text-start font-medium">
                            {t('bildirim.olayBaslik')}
                          </th>
                          {veri.kanallar.map((k) => (
                            <th key={k} scope="col" className="px-2 py-2 text-center font-medium">
                              {t(`bildirim.kanal.${k}`)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {olaylar.map((o) => (
                          <tr key={o.olay} className="border-b border-white/5">
                            <th scope="row" className="py-2.5 pe-3 text-start font-normal">
                              {t(`bildirim.olay.${o.olay}`)}
                              {!o.tetikleniyor && (
                                <span
                                  className="ms-2 rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                                  title={t('bildirim.matris.yakindaAciklama')}
                                >
                                  {t('bildirim.matris.yakinda')}
                                </span>
                              )}
                            </th>
                            {veri.kanallar.map((k) => (
                              <td key={k} className="px-2 py-2.5 text-center">
                                <span className="inline-flex items-center gap-1">
                                  <Anahtar
                                    acik={k === 'inapp' ? true : Boolean(taslak[rol]?.[o.olay]?.[k])}
                                    pasif={k === 'inapp'}
                                    onDegis={(d) => degistir(rol, o.olay, k, d)}
                                    etiket={`${t(`bildirim.olay.${o.olay}`)} · ${t(`bildirim.kanal.${k}`)}`}
                                    testId={`matris-${rol}-${o.olay}-${k}`}
                                    ipucu={k === 'inapp' ? t('bildirim.inappKilitli') : undefined}
                                  />
                                  {k === 'inapp' && <Lock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />}
                                </span>
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}

            <Button
              type="button"
              onClick={() => void kaydet()}
              disabled={kaydediliyor}
              className="gap-2"
              data-testid="bildirim-matris-kaydet"
            >
              {kaydediliyor ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Save className="h-4 w-4" aria-hidden="true" />
              )}
              {t('bildirim.matris.kaydet')}
            </Button>
          </div>
        )}
      </section>

      <BildirimTercihleri key={surum} baslik={t('bildirim.kendiTercihlerim')} genis />
    </div>
  );
}
