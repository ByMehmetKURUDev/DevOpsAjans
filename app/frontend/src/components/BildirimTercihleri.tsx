import { useCallback, useEffect, useMemo, useState } from 'react';
import { BellRing, Info, Loader2, Lock, MoonStar, RefreshCw, Save, Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  KANALLAR,
  tercihlerimiGetir,
  tercihlerimiKaydet,
  type Hucre,
  type Kanal,
  type Tercihlerim,
} from '@/lib/bildirim';
import {
  PushHatasi,
  bildirimleriAc,
  bildirimleriKapat,
  denemeBildirimi,
  iosMu,
  izinDurumu,
  mevcutAbonelik,
  pushDestegi,
} from '@/lib/webPush';

/**
 * Bildirim tercihleri — müşteri paneli › Profil ve yönetici › Bildirimler.
 *
 * Satırlar olay, sütunlar kanal. Bir anahtar üç sebeple pasif olabilir:
 *  - panel içi: kapatılamaz;
 *  - yönetici matrisi o kanalı bu olay için kapatmış (kişi açamaz);
 *  - kanal sunucuda kurulmamış ya da yönetici kanalı tümden kapatmış.
 * Liste ve kurallar sunucudan geliyor (jetondaki e-posta ve rol).
 */

interface Props {
  /** Yönetici panelinde farklı başlıkla, geniş gösterim. */
  baslik?: string;
  genis?: boolean;
}

type Taslak = Record<string, Hucre>;

export function Anahtar({
  acik,
  pasif,
  onDegis,
  etiket,
  testId,
  ipucu,
}: {
  acik: boolean;
  pasif: boolean;
  onDegis: (d: boolean) => void;
  etiket: string;
  testId: string;
  ipucu?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={acik}
      aria-label={etiket}
      title={ipucu || etiket}
      disabled={pasif}
      data-testid={testId}
      onClick={() => onDegis(!acik)}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400 ${
        acik ? 'border-purple-400/60 bg-purple-500/70' : 'border-white/15 bg-white/10'
      } ${pasif ? 'cursor-not-allowed opacity-40' : 'cursor-pointer hover:border-purple-400'}`}
    >
      <span
        aria-hidden="true"
        className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
          acik ? 'translate-x-[18px] rtl:-translate-x-[18px]' : 'translate-x-[2px] rtl:-translate-x-[2px]'
        }`}
      />
    </button>
  );
}

export default function BildirimTercihleri({ baslik, genis = false }: Props) {
  const { t } = useTranslation();
  const [veri, setVeri] = useState<Tercihlerim | null>(null);
  const [taslak, setTaslak] = useState<Taslak>({});
  const [sessizAcik, setSessizAcik] = useState(false);
  const [sessiz, setSessiz] = useState({ bas: '22:00', bit: '08:00' });
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState(false);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  const [abone, setAbone] = useState(false);
  const [pushIsleniyor, setPushIsleniyor] = useState(false);
  const [deneniyor, setDeneniyor] = useState(false);
  const destek = useMemo(() => pushDestegi(), []);

  const uygula = useCallback((v: Tercihlerim) => {
    setVeri(v);
    setTaslak(Object.fromEntries(v.olaylar.map((o) => [o.olay, { ...o.acik }])));
    setSessizAcik(Boolean(v.sessiz_saatler));
    if (v.sessiz_saatler) setSessiz(v.sessiz_saatler);
  }, []);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setHata(false);
    try {
      uygula(await tercihlerimiGetir());
      setAbone(Boolean(await mevcutAbonelik()));
    } catch {
      setHata(true);
    } finally {
      setYukleniyor(false);
    }
  }, [uygula]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kanalKullanilir = (k: Kanal) => veri?.kanal_durumu[k] === 'hazir';

  const degistir = (olay: string, kanal: Kanal, deger: boolean) =>
    setTaslak((eski) => ({ ...eski, [olay]: { ...eski[olay], [kanal]: deger } }));

  const kaydet = async () => {
    if (!veri) return;
    setKaydediliyor(true);
    try {
      const tercih: Record<string, Partial<Hucre>> = {};
      for (const o of veri.olaylar) {
        const hucre: Partial<Hucre> = {};
        for (const k of KANALLAR) {
          if (k === 'inapp' || !o.izin[k]) continue;
          hucre[k] = Boolean(taslak[o.olay]?.[k]);
        }
        tercih[o.olay] = hucre;
      }
      uygula(await tercihlerimiKaydet(tercih, sessizAcik ? sessiz : null));
      toast.success(t('bildirim.kaydedildi'));
    } catch {
      toast.error(t('bildirim.kaydedilemedi'));
    } finally {
      setKaydediliyor(false);
    }
  };

  const pushAcKapat = async () => {
    setPushIsleniyor(true);
    try {
      if (abone) {
        await bildirimleriKapat();
        setAbone(false);
        toast.success(t('bildirim.push.kapatildi'));
      } else {
        await bildirimleriAc(veri?.push.anahtar);
        setAbone(true);
        toast.success(t('bildirim.push.acildi'));
      }
      const yeni = await tercihlerimiGetir().catch(() => null);
      if (yeni) setVeri(yeni);
    } catch (e) {
      const kod = e instanceof PushHatasi ? e.kod : '';
      toast.error(kod === 'izin-yok' ? t('bildirim.push.izinReddedildi') : t('bildirim.push.hata'));
    } finally {
      setPushIsleniyor(false);
    }
  };

  const dene = async () => {
    setDeneniyor(true);
    try {
      const sonuc = await denemeBildirimi();
      if (sonuc.durum === 'sent') toast.success(t('bildirim.push.denendi'));
      else toast.error(`${t('bildirim.push.denemeHata')}${sonuc.ayrinti ? ` — ${sonuc.ayrinti}` : ''}`);
    } catch {
      toast.error(t('bildirim.push.denemeHata'));
    } finally {
      setDeneniyor(false);
    }
  };

  const pushBolumu = () => {
    if (!veri) return null;
    let metin: string;
    let dugme = false;
    if (!veri.push.yapilandirildi) metin = t('bildirim.push.yapilandirilmadi');
    else if (destek === 'ios-ana-ekran') metin = t('bildirim.push.ios');
    else if (destek === 'yok') metin = t('bildirim.push.destekYok');
    else if (izinDurumu() === 'denied') metin = t('bildirim.push.izinReddedildi');
    else {
      metin = abone ? t('bildirim.push.acik') : t('bildirim.push.kapaliDurum');
      dugme = true;
    }
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4" data-testid="bildirim-push">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <BellRing className="h-4 w-4 text-purple-400" aria-hidden="true" />
          {t('bildirim.push.baslik')}
        </p>
        <p className="mt-1 text-xs text-muted-foreground" data-testid="bildirim-push-durum">
          {metin}
        </p>
        {dugme && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant={abone ? 'outline' : 'default'}
              onClick={() => void pushAcKapat()}
              disabled={pushIsleniyor}
              className="gap-2"
              data-testid="bildirim-push-dugme"
            >
              {pushIsleniyor ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <BellRing className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {abone ? t('bildirim.push.kapat') : t('bildirim.push.ac')}
            </Button>
            {abone && (
              <Button type="button" size="sm" variant="outline" onClick={() => void dene()} disabled={deneniyor} className="gap-2">
                {deneniyor ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Send className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {t('bildirim.push.dene')}
              </Button>
            )}
          </div>
        )}
        {veri.push.yapilandirildi && destek === 'var' && iosMu() && (
          <p className="mt-2 text-[11px] text-muted-foreground">{t('bildirim.push.ios')}</p>
        )}
      </div>
    );
  };

  return (
    <section
      className={`cam-kart rounded-2xl border border-white/10 bg-white/[0.03] p-6 ${genis ? '' : 'max-w-3xl'}`}
      aria-labelledby="bildirim-tercihleri-baslik"
      data-testid="bildirim-tercihleri"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="bildirim-tercihleri-baslik" className="flex items-center gap-2 text-lg font-semibold">
            <BellRing className="h-5 w-5 text-purple-400" aria-hidden="true" />
            {baslik || t('bildirim.baslik')}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">{t('bildirim.aciklama')}</p>
        </div>
        <Button variant="outline" size="icon" onClick={() => void yukle()} aria-label={t('bildirim.yenile')}>
          <RefreshCw className={`h-4 w-4 ${yukleniyor ? 'animate-spin' : ''}`} aria-hidden="true" />
        </Button>
      </div>

      {yukleniyor && !veri ? (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        </div>
      ) : hata || !veri ? (
        <p className="py-4 text-sm text-red-300">{t('bildirim.hata')}</p>
      ) : (
        <div className="space-y-5">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[30rem] border-collapse text-sm" data-testid="bildirim-tablo">
              <thead>
                <tr className="border-b border-white/10 text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pe-3 text-start font-medium">
                    {t('bildirim.olayBaslik')}
                  </th>
                  {veri.kanallar.map((k) => (
                    <th key={k} scope="col" className="px-2 py-2 text-center font-medium">
                      <span className="block">{t(`bildirim.kanal.${k}`)}</span>
                      {k !== 'inapp' && !kanalKullanilir(k) && (
                        <span
                          className="mt-0.5 block text-[10px] font-normal text-amber-300/80"
                          data-testid={`bildirim-kanal-durum-${k}`}
                        >
                          {t(`bildirim.durum.${veri.kanal_durumu[k]}`)}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {veri.olaylar.map((o) => (
                  <tr key={o.olay} className="border-b border-white/5" data-testid={`bildirim-satir-${o.olay}`}>
                    <th scope="row" className="py-2.5 pe-3 text-start font-normal">
                      {t(`bildirim.olay.${o.olay}`)}
                    </th>
                    {veri.kanallar.map((k) => {
                      const inapp = k === 'inapp';
                      const izinYok = !o.izin[k];
                      const kullanilamaz = !inapp && !kanalKullanilir(k);
                      const ipucu = inapp
                        ? t('bildirim.inappKilitli')
                        : izinYok
                          ? t('bildirim.yoneticiKapatti')
                          : kullanilamaz
                            ? t('bildirim.kanalKullanilamaz')
                            : undefined;
                      return (
                        <td key={k} className="px-2 py-2.5 text-center">
                          <span className="inline-flex items-center gap-1">
                            <Anahtar
                              // Kullanılamayan kanal kapalı görünür (gönderilmeyecek); kişinin
                              // kaydı yine saklı kalır, kanal kurulunca geri gelir.
                              acik={inapp ? true : izinYok || kullanilamaz ? false : Boolean(taslak[o.olay]?.[k])}
                              pasif={inapp || izinYok || kullanilamaz}
                              onDegis={(d) => degistir(o.olay, k, d)}
                              etiket={`${t(`bildirim.olay.${o.olay}`)} · ${t(`bildirim.kanal.${k}`)}`}
                              testId={`bildirim-${o.olay}-${k}`}
                              ipucu={ipucu}
                            />
                            {(inapp || izinYok) && (
                              <Lock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                            )}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="flex items-start gap-2 text-[11px] text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>{t('bildirim.lejant')}</span>
          </p>

          <div className="grid gap-4 md:grid-cols-2">
            {pushBolumu()}

            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
                <input
                  type="checkbox"
                  checked={sessizAcik}
                  onChange={(e) => setSessizAcik(e.target.checked)}
                  className="h-4 w-4 accent-purple-500"
                  data-testid="bildirim-sessiz"
                />
                <MoonStar className="h-4 w-4 text-purple-400" aria-hidden="true" />
                {t('bildirim.sessiz.baslik')}
              </label>
              <p className="mt-1 text-xs text-muted-foreground">{t('bildirim.sessiz.aciklama')}</p>
              {sessizAcik && (
                <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                  <label className="flex items-center gap-2">
                    {t('bildirim.sessiz.bas')}
                    <input
                      type="time"
                      value={sessiz.bas}
                      onChange={(e) => setSessiz((s) => ({ ...s, bas: e.target.value }))}
                      className="h-8 rounded-lg border border-white/10 bg-white/5 px-2 text-sm"
                    />
                  </label>
                  <label className="flex items-center gap-2">
                    {t('bildirim.sessiz.bit')}
                    <input
                      type="time"
                      value={sessiz.bit}
                      onChange={(e) => setSessiz((s) => ({ ...s, bit: e.target.value }))}
                      className="h-8 rounded-lg border border-white/10 bg-white/5 px-2 text-sm"
                    />
                  </label>
                </div>
              )}
            </div>
          </div>

          <Button
            type="button"
            onClick={() => void kaydet()}
            disabled={kaydediliyor}
            className="gap-2"
            data-testid="bildirim-kaydet"
          >
            {kaydediliyor ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Save className="h-4 w-4" aria-hidden="true" />
            )}
            {t('bildirim.kaydet')}
          </Button>
        </div>
      )}
    </section>
  );
}
