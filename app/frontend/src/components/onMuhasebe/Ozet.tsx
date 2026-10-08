import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ArrowDownLeft, ArrowLeftRight, ArrowUpRight, CreditCard, Landmark, Store, Wallet } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { HareketFormu, VirmanFormu } from '@/components/onMuhasebe/Form';
import Oneriler from '@/components/onMuhasebe/Oneriler';
import { Bos, HataSatiri, KART, Not, Rozet, Tutar, Yukleniyor } from '@/components/onMuhasebe/ortak';
import { gunYaz, hataMetni, kategoriAdi, para, TUR_RENGI, type BolumProps, type HareketTuru, type Ozet as OzetVerisi } from '@/lib/onMuhasebe';

const HESAP_IKONU = { kasa: Wallet, banka: Landmark, kredi_karti: CreditCard, pos: Store } as const;

/** Faz 6M — özet: bakiyeler, bu ay gelir/gider, bütçe uyarıları, onay bekleyen öneriler, vadesi geçen alacak, hesaplar,
 * son hareketler. `muhasebe_okur` (yalnız rapor) son hareketleri ve ayrıntı bölümlerine bağlantıları görmez. */
export default function Ozet({ api, meta, yenile, surum, git }: BolumProps) {
  const { t, i18n } = useTranslation();
  const dil = i18n.language || 'tr';
  const [ozet, setOzet] = useState<OzetVerisi | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [form, setForm] = useState<HareketTuru | 'virman' | null>(null);
  const salt = meta.salt_okunur;
  const okur = meta.okur;

  const yukle = useCallback(async () => {
    setHata(null);
    try {
      setOzet(await api.ozet());
    } catch (e) {
      setHata(hataMetni(t, e));
    }
  }, [api, t]);

  useEffect(() => {
    void yukle();
  }, [yukle, surum]);

  const kaydedildi = () => {
    setForm(null);
    yenile();
  };

  if (!ozet) return hata ? <HataSatiri hata={hata} /> : <Yukleniyor />;
  const aktifHesaplar = meta.hesaplar.filter((h) => !h.arsiv);
  return (
    <div className="space-y-4" data-testid="mh-ozet">
      {!salt && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" className="gap-1.5" onClick={() => setForm('gelir')} data-testid="mh-hizli-gelir">
            <ArrowDownLeft className="h-4 w-4" aria-hidden="true" />
            {t('onMuhasebe.ozet.hizliGelir')}
          </Button>
          <Button type="button" size="sm" variant="outline" className="gap-1.5 !bg-transparent border-white/20" onClick={() => setForm('gider')} data-testid="mh-hizli-gider">
            <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
            {t('onMuhasebe.ozet.hizliGider')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="gap-1.5 !bg-transparent border-white/20"
            onClick={() => setForm('virman')}
            disabled={aktifHesaplar.length < 2}
            data-testid="mh-hizli-virman"
          >
            <ArrowLeftRight className="h-4 w-4" aria-hidden="true" />
            {t('onMuhasebe.ozet.hizliVirman')}
          </Button>
        </div>
      )}
      {!aktifHesaplar.length && (
        <Not testid="mh-hesap-yok">
          {t('onMuhasebe.ozet.hesapYok')}{' '}
          {!salt && (
            <button type="button" className="underline" onClick={() => git('hesaplar')}>
              {t('onMuhasebe.ozet.hesapEkle')}
            </button>
          )}
        </Not>
      )}
      {ozet.butce.asim_sayisi > 0 && (
        <p className="flex items-start gap-2 rounded-xl border border-rose-400/40 bg-rose-500/10 p-3 text-sm text-rose-100" role="alert" data-testid="mh-ozet-butce-asim">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          <span>
            {t('onMuhasebe.butce.asimUyari', { sayi: ozet.butce.asim_sayisi })}{' '}
            <button type="button" className="underline" onClick={() => git('butce')}>
              {t('onMuhasebe.bolum.butce')}
            </button>
          </span>
        </p>
      )}
      {!okur && <Oneriler api={api} meta={meta} yenile={yenile} surum={surum} />}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className={`${KART} p-4`} data-testid="mh-ozet-bakiye">
          <p className="text-xs text-muted-foreground">{t('onMuhasebe.ozet.bakiyeler')}</p>
          {ozet.bakiyeler.length ? (
            ozet.bakiyeler.map((b) => (
              <p key={b.para_birimi} className="mt-1 text-xl font-semibold">
                <Tutar deger={b.bakiye} metin={para(b.bakiye, b.para_birimi, dil)} notr={b.bakiye >= 0} />
              </p>
            ))
          ) : (
            <p className="mt-1 text-xl font-semibold">—</p>
          )}
        </div>
        <div className={`${KART} p-4`}>
          <p className="text-xs text-muted-foreground">{t('onMuhasebe.ozet.buAyGelir')}</p>
          {ozet.bu_ay.length ? (
            ozet.bu_ay.map((b) => (
              <p key={b.para_birimi} className="mt-1 text-xl font-semibold text-emerald-300" data-testid="mh-ozet-gelir">
                {para(b.gelir, b.para_birimi, dil)}
              </p>
            ))
          ) : (
            <p className="mt-1 text-xl font-semibold">—</p>
          )}
        </div>
        <div className={`${KART} p-4`}>
          <p className="text-xs text-muted-foreground">{t('onMuhasebe.ozet.buAyGider')}</p>
          {ozet.bu_ay.length ? (
            ozet.bu_ay.map((b) => (
              <p key={b.para_birimi} className="mt-1 text-xl font-semibold text-rose-300" data-testid="mh-ozet-gider">
                {para(b.gider, b.para_birimi, dil)}
              </p>
            ))
          ) : (
            <p className="mt-1 text-xl font-semibold">—</p>
          )}
        </div>
        <div className={`${KART} p-4`}>
          <p className="text-xs text-muted-foreground">{t('onMuhasebe.ozet.gecikmisAlacak')}</p>
          {ozet.gecikmis_alacak.length ? (
            <>
              {ozet.gecikmis_alacak.map((b) => (
                <p key={b.para_birimi} className="mt-1 text-xl font-semibold text-amber-200">
                  {para(b.tutar, b.para_birimi, dil)}
                </p>
              ))}
              {okur ? (
                <p className="mt-1 text-xs text-muted-foreground">{t('onMuhasebe.ozet.gecikmisCari', { sayi: ozet.gecikmis_cari })}</p>
              ) : (
                <button type="button" className="mt-1 text-xs text-muted-foreground underline" onClick={() => git('cariler')}>
                  {t('onMuhasebe.ozet.gecikmisCari', { sayi: ozet.gecikmis_cari })}
                </button>
              )}
            </>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">{t('onMuhasebe.ozet.gecikmisYok')}</p>
          )}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className={`${KART} p-4`}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="font-semibold">{t('onMuhasebe.bolum.hesaplar')}</h3>
            {!okur && (
              <button type="button" className="text-xs text-muted-foreground underline" onClick={() => git('hesaplar')}>
                {t('onMuhasebe.ortak.tumu')}
              </button>
            )}
          </div>
          {aktifHesaplar.length ? (
            <ul className="divide-y divide-white/5">
              {aktifHesaplar.map((h) => {
                const Ikon = HESAP_IKONU[h.tur];
                return (
                  <li key={h.id} className="flex items-center justify-between gap-3 py-2 text-sm" data-testid="mh-ozet-hesap">
                    <span className="flex min-w-0 items-center gap-2">
                      <Ikon className="h-4 w-4 flex-none text-purple-300" aria-hidden="true" />
                      <span className="truncate">{h.ad}</span>
                    </span>
                    <Tutar deger={h.bakiye} metin={para(h.bakiye, h.para_birimi, dil)} notr={h.bakiye >= 0} />
                  </li>
                );
              })}
            </ul>
          ) : (
            <Bos>{t('onMuhasebe.hesap.bos')}</Bos>
          )}
          {ozet.butce.uyarilar.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-1 text-sm font-semibold">{t('onMuhasebe.ozet.butceUyarilari')}</h4>
              <ul className="space-y-1">
                {ozet.butce.uyarilar.map((b) => (
                  <li key={`${b.kategori_id}-${b.para_birimi}`} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate">{kategoriAdi(t, b)}</span>
                    <Rozet renk={b.durum === 'asildi' ? 'border-rose-400/40 bg-rose-500/15 text-rose-200' : 'border-amber-400/40 bg-amber-500/15 text-amber-200'}>
                      {t(`onMuhasebe.butce.durum.${b.durum}`)} · %{b.oran}
                    </Rozet>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        {!okur && (
        <div className={`${KART} p-4`}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="font-semibold">{t('onMuhasebe.ozet.sonHareketler')}</h3>
            <button type="button" className="text-xs text-muted-foreground underline" onClick={() => git('hareketler')}>
              {t('onMuhasebe.ortak.tumu')}
            </button>
          </div>
          {ozet.son_hareketler.length ? (
            <ul className="divide-y divide-white/5" data-testid="mh-ozet-son">
              {ozet.son_hareketler.map((h) => (
                <li key={h.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <Rozet renk={TUR_RENGI[h.tur]}>{t(`onMuhasebe.tur.${h.tur}`)}</Rozet>
                      <span className="truncate">{h.aciklama || (h.kategori ? kategoriAdi(t, h.kategori) : h.cari || '—')}</span>
                    </span>
                    <span className="text-xs text-muted-foreground">{gunYaz(h.tarih, dil)}</span>
                  </span>
                  <Tutar
                    deger={h.tur === 'gelir' || h.tur === 'tahsilat' ? h.tutar : h.tur === 'virman' ? 0 : -h.tutar}
                    metin={para(h.tutar, h.para_birimi, dil)}
                    notr={h.tur === 'virman'}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <Bos>{t('onMuhasebe.ozet.hareketYok')}</Bos>
          )}
        </div>
        )}
      </div>
      {form === 'virman' ? (
        <VirmanFormu api={api} meta={meta} onKaydet={kaydedildi} onKapat={() => setForm(null)} />
      ) : form ? (
        <HareketFormu api={api} meta={meta} varsayilanTur={form} onKaydet={kaydedildi} onKapat={() => setForm(null)} />
      ) : null}
    </div>
  );
}
