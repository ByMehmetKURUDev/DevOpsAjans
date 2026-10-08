import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, CheckCheck, EyeOff, Inbox, Loader2, Undo2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { DIS_DUGME, HataSatiri, KART, Rozet, SECIM } from '@/components/onMuhasebe/ortak';
import { dar, gunYaz, hataMetni, kategoriAdi, para, TUR_RENGI, type BolumProps, type Oneri } from '@/lib/onMuhasebe';

type Gorunum = 'bekliyor' | 'yoksayildi';

/**
 * Faz 6M — onay bekleyen otomatik yansımalar. Kaynak ayarında "onayıma sun" açıksa (hukuk masrafı ve saha işi
 * varsayılan) ve ödeme kaydı olmadan "ödendi" işaretlenen faturalarda kayıt önce burada bekler: onaylanınca
 * (istenirse başka hesaba) deftere yazılır — aynı kaynak kimliğiyle, iki kez sayılmaz; yok sayılan kaynağı değişmedikçe
 * yeniden önerilmez (ör. ekstreden zaten içe aktarıldıysa). Hiç öneri yoksa hiçbir şey göstermez.
 */
export default function Oneriler({ api, meta, yenile, surum }: Pick<BolumProps, 'api' | 'meta' | 'yenile' | 'surum'>) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const salt = meta.salt_okunur;
  const [gorunum, setGorunum] = useState<Gorunum>('bekliyor');
  const [liste, setListe] = useState<Oneri[] | null>(null);
  const [sayilar, setSayilar] = useState<Record<Gorunum, number>>({ bekliyor: 0, yoksayildi: 0 });
  const [hesapSecimi, setHesapSecimi] = useState<Record<number, string>>({});
  const [mesgul, setMesgul] = useState<number | 'toplu' | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [mesaj, setMesaj] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    try {
      const r = await api.oneriler(gorunum);
      setListe(r.items);
      setSayilar(r.sayilar);
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, gorunum, t]);

  useEffect(() => {
    void yukle();
  }, [yukle, surum]);

  const calis = async (kimlik: number | 'toplu', is: () => Promise<unknown>, basari?: string) => {
    setHata(null);
    setMesaj(null);
    setMesgul(kimlik);
    try {
      await is();
      if (basari) setMesaj(basari);
      await yukle();
      yenile();
    } catch (e) {
      setHata(hataMetni(t, e));
    } finally {
      setMesgul(null);
    }
  };

  if (!liste || (sayilar.bekliyor === 0 && sayilar.yoksayildi === 0)) return null;
  const hesaplar = meta.hesaplar.filter((h) => !h.arsiv);

  const onayla = (o: Oneri) => {
    const secim = hesapSecimi[o.id];
    const g: Record<string, unknown> = {};
    if (secim !== undefined && secim !== '' && Number(secim) !== o.hesap_id) g.hesap_id = Number(secim);
    void calis(o.id, () => api.oneriOnayla(o.id, g), t('onMuhasebe.oneri.onaylandi', { sayi: 1 }));
  };

  return (
    <section className={`${KART} space-y-3 border-amber-400/30 p-4`} data-testid="mh-oneriler" aria-labelledby="mh-oneri-baslik">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 font-semibold" id="mh-oneri-baslik">
            <Inbox className="h-4 w-4 text-amber-200" aria-hidden="true" />
            {t('onMuhasebe.oneri.baslik', { sayi: sayilar.bekliyor })}
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{t('onMuhasebe.oneri.aciklama')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!salt && gorunum === 'bekliyor' && liste.length > 1 && (
            <Button
              type="button"
              size="sm"
              className="gap-1.5"
              disabled={mesgul !== null}
              onClick={() =>
                void calis(
                  'toplu',
                  async () => {
                    const r = await api.oneriToplu('onayla', liste.map((o) => o.id));
                    if (r.hatalar.length) setHata(t('onMuhasebe.oneri.topluHata', { sayi: r.hatalar.length }));
                  },
                  t('onMuhasebe.oneri.onaylandi', { sayi: liste.length })
                )
              }
              data-testid="mh-oneri-tumu"
            >
              {mesgul === 'toplu' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <CheckCheck className="h-4 w-4" aria-hidden="true" />}
              {t('onMuhasebe.oneri.tumunuOnayla')}
            </Button>
          )}
          {(sayilar.yoksayildi > 0 || gorunum === 'yoksayildi') && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className={DIS_DUGME}
              onClick={() => setGorunum((g) => (g === 'bekliyor' ? 'yoksayildi' : 'bekliyor'))}
              data-testid="mh-oneri-gorunum"
            >
              {gorunum === 'bekliyor' ? t('onMuhasebe.oneri.yoksayilanlar', { sayi: sayilar.yoksayildi }) : t('onMuhasebe.oneri.bekleyenler', { sayi: sayilar.bekliyor })}
            </Button>
          )}
        </div>
      </div>
      <HataSatiri hata={hata} />
      {mesaj && (
        <p className="text-sm text-emerald-300" role="status">
          {mesaj}
        </p>
      )}
      {liste.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">{t('onMuhasebe.oneri.bos')}</p>
      ) : (
        <ul className="divide-y divide-white/5">
          {liste.map((o) => {
            const uygun = hesaplar.filter((h) => h.para_birimi === o.para_birimi);
            const secim = hesapSecimi[o.id] ?? (o.hesap_id ? String(o.hesap_id) : '');
            return (
              <li key={o.id} className="flex flex-col gap-2 py-3 text-sm lg:flex-row lg:items-center" data-testid="mh-oneri" data-kaynak={o.kaynak}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Rozet renk={TUR_RENGI[o.tur]}>{t(`onMuhasebe.tur.${o.tur}`)}</Rozet>
                    <Rozet>{t(`onMuhasebe.kaynak.${o.kaynak}`, { defaultValue: o.kaynak })}</Rozet>
                    <span className="truncate font-medium">{o.aciklama || kategoriAdi(t, o.kategori)}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {gunYaz(o.tarih, dil)}
                    {o.belge_no ? ` · ${o.belge_no}` : ''}
                    {o.cari ? ` · ${o.cari}` : ''}
                    {o.kategori ? ` · ${kategoriAdi(t, o.kategori)}` : ''}
                    {o.kdv_tutari ? ` · ${t('onMuhasebe.oneri.kdv', { tutar: para(o.kdv_tutari, o.para_birimi, dil) })}` : ''}
                  </p>
                </div>
                <span className={`whitespace-nowrap text-base font-semibold tabular-nums ${o.tur === 'gelir' ? 'text-emerald-300' : 'text-rose-300'}`}>
                  {para(o.tutar, o.para_birimi, dil)}
                </span>
                {!salt && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {gorunum === 'bekliyor' ? (
                      <>
                        <select
                          className={dar(SECIM, 'w-44')}
                          value={secim}
                          aria-label={t('onMuhasebe.oneri.hesap')}
                          onChange={(e) => setHesapSecimi((x) => ({ ...x, [o.id]: e.target.value }))}
                          data-testid="mh-oneri-hesap"
                        >
                          {!o.hesap_id && <option value="">{t('onMuhasebe.oneri.vadeli')}</option>}
                          {uygun.map((h) => (
                            <option key={h.id} value={h.id}>
                              {h.ad}
                            </option>
                          ))}
                        </select>
                        <Button type="button" size="sm" className="h-9 gap-1" disabled={mesgul !== null} onClick={() => onayla(o)} data-testid="mh-oneri-onayla">
                          {mesgul === o.id ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Check className="h-4 w-4" aria-hidden="true" />}
                          {t('onMuhasebe.oneri.onayla')}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-9 gap-1 px-2"
                          disabled={mesgul !== null}
                          onClick={() => void calis(o.id, () => api.oneriYoksay(o.id))}
                          data-testid="mh-oneri-yoksay"
                        >
                          <EyeOff className="h-4 w-4" aria-hidden="true" />
                          {t('onMuhasebe.oneri.yoksay')}
                        </Button>
                      </>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-9 gap-1 px-2"
                        disabled={mesgul !== null}
                        onClick={() => void calis(o.id, () => api.oneriGeriAl(o.id))}
                        data-testid="mh-oneri-geri-al"
                      >
                        <Undo2 className="h-4 w-4" aria-hidden="true" />
                        {t('onMuhasebe.oneri.geriAl')}
                      </Button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
